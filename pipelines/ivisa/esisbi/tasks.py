# -*- coding: utf-8 -*-
"""Tasks do e-SISBI — varredura completa do recorte via API pública.

6 chamadas por estabelecimento (detalhe + responsáveis + classificações +
capacidades + escopos + produtos). O `kind="sweep_completo"` no fim só é
enviado se a varredura inteira terminou sem erro — senão o COREVISA não teria
como distinguir "sumiu de verdade" de "não deu pra visitar" e marcaria removido
à toa.
"""

import asyncio
import unicodedata
import uuid
from datetime import UTC, datetime
from typing import Any

from prefect import task

from pipelines.ivisa._shared.corevisa import ItemLote, RunMeta, enviar_lote
from pipelines.utils.logger import log

from .client import EsisbiApiClient, EsisbiIndisponivel
from .constants import constants as C


def _normalizar(texto: str | None) -> str:
  sem_acento = (
    unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
  )
  return sem_acento.strip().upper()


def _int_ou_none(valor: Any) -> int | None:
  try:
    return int(valor)
  except (TypeError, ValueError):
    return None


async def _coletar_ficha(cliente: EsisbiApiClient, id_estab: int) -> dict[str, Any]:
  recurso = C.RECURSO_ESTAB.value
  detalhe = await cliente.obter(recurso, id_estab)
  responsaveis = await cliente.listar(
    "estabelecimentos-sisbi-pessoa", idEstabSisbi=id_estab
  )
  classificacoes = await cliente.listar(
    "estabs-sisbi-classificacoes", idEstabSisbi=id_estab
  )
  capacidades = await cliente.listar("estabs-capacidades", idEstabSisbi=id_estab)
  escopos = await cliente.listar("estabs-sisbi-escopos", idEstabSisbi=id_estab)
  produtos = await cliente.listar("produtos-sisbi", idEstabelecimentoSisbi=id_estab)
  return {
    "detalhe": detalhe,
    "responsaveis": responsaveis,
    "classificacoes": classificacoes,
    "capacidades": capacidades,
    "escopos": escopos,
    "produtos": produtos,
  }


async def _varrer(environment: str) -> dict:
  recurso = C.RECURSO_ESTAB.value
  uf = C.UF.value.strip().upper() or None
  municipios_norm = {_normalizar(m) for m in C.MUNICIPIOS.value}
  page_size = max(1, C.PAGE_SIZE.value)
  delay_s = max(0, C.SYNC_DELAY_MS.value) / 1000

  run_id = f"esisbi-{uuid.uuid4().hex[:12]}"
  buscou_em = datetime.now(UTC)
  itens: list[ItemLote] = []
  houve_erro = False

  async with EsisbiApiClient() as cliente:
    try:
      total = await cliente.contar(recurso, sgUf=uf)
    except EsisbiIndisponivel as exc:
      log(f"esisbi: falha ao contar recorte: {exc}", level="error")
      return enviar_lote(
        C.FONTE.value, _run_meta(run_id, buscou_em), [], environment=environment
      )

    paginas = (total + page_size - 1) // page_size if total else 0
    log(
      f"esisbi: {total} estabelecimento(s) sgUf={uf} ({paginas} página(s))", level="info"
    )

    for pagina in range(1, paginas + 1):
      try:
        lote_pagina = await cliente.listar(recurso, page=pagina, count=page_size, sgUf=uf)
      except EsisbiIndisponivel as exc:
        houve_erro = True
        log(f"esisbi: falha na página {pagina}: {exc}", level="warning")
        continue

      for item in lote_pagina:
        if (
          municipios_norm and _normalizar(item.get("nmMunicipio")) not in municipios_norm
        ):
          continue
        id_estab = _int_ou_none(item.get("idEstabSisbi"))
        if id_estab is None:
          continue
        try:
          ficha = await _coletar_ficha(cliente, id_estab)
        except EsisbiIndisponivel as exc:
          houve_erro = True
          log(f"esisbi: falha no estabelecimento {id_estab}: {exc}", level="warning")
          continue
        itens.append(ItemLote(kind="scan", source_ref=str(id_estab), conteudo=ficha))
        if delay_s:
          await asyncio.sleep(delay_s)

  if not houve_erro and itens:
    itens.append(ItemLote(kind="sweep_completo", conteudo={"uf": uf}))
  elif houve_erro:
    log("esisbi: varredura incompleta — sweep_completo NÃO enviado", level="warning")

  resultado = enviar_lote(
    C.FONTE.value, _run_meta(run_id, buscou_em), itens, environment=environment
  )
  log(f"esisbi: {len(itens)} item(ns) enviado(s) ao COREVISA — {resultado}", level="info")
  return resultado


def _run_meta(run_id: str, buscou_em: datetime) -> RunMeta:
  return RunMeta(
    robo="esisbi-flow", run_id=run_id, buscou_em=buscou_em, terminou_em=datetime.now(UTC)
  )


@task(name="esisbi-varrer-recorte")
def varrer_recorte(environment: str) -> dict:
  return asyncio.run(_varrer(environment))
