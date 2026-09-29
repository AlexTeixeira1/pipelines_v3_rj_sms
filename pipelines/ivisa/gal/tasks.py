# -*- coding: utf-8 -*-
"""Tasks do GAL — varredura do grid lista-finais + download do PDF de cada laudo
dentro do recorte de município.

Cru vai para POST /v1/ingestao/gal/lote: `kind="laudo"` com
`conteudo={"grid": <linha crua>}` + blob PDF. O COREVISA parseia o laudo.

O cookie de sessão vem do Infisical (GAL_SESSAO_COOKIE, JSON). Quando expira,
a task falha com GalSessaoExpirada → alerta Discord → operador renova o secret.
"""

import asyncio
import json
import unicodedata
import uuid
from datetime import UTC, datetime
from typing import Any

from prefect import task

from pipelines.ivisa._shared.corevisa import ItemLote, RunMeta, enviar_lote
from pipelines.utils.infisical import get_secret
from pipelines.utils.logger import log

from .client import GalSessaoExpirada, GalSessaoWeb, GalWebError
from .constants import constants as C

INFISICAL_PATH = "/ivisa-rio"


def _normalizar(texto: str) -> str:
  sem_acento = (
    unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
  )
  return sem_acento.strip().upper()


def _carregar_cookies(environment: str) -> list[dict[str, Any]]:
  bruto = get_secret(
    path=INFISICAL_PATH, secret_name=C.SECRET_COOKIE.value, environment=environment
  )
  try:
    dados = json.loads(bruto)
  except ValueError as exc:
    raise GalWebError(f"GAL_SESSAO_COOKIE no Infisical não é JSON válido: {exc}") from exc
  if isinstance(dados, dict):
    return list(dados.get("cookies") or [])
  return list(dados) if isinstance(dados, list) else []


async def _varrer_grid(
  sessao: GalSessaoWeb, pagina_tamanho: int, limite_paginas: int | None
) -> list[dict[str, Any]]:
  linhas_todas: list[dict[str, Any]] = []
  start = 0
  paginas = 0
  while True:
    linhas, total = await sessao.lista_finais(start=start, limit=pagina_tamanho)
    if not linhas:
      break
    paginas += 1
    linhas_todas.extend(linhas)
    start += pagina_tamanho
    if limite_paginas and paginas >= limite_paginas:
      break
    if start >= total:
      break
  return linhas_todas


async def _varrer(
  pagina_tamanho: int, limite_paginas: int | None, environment: str
) -> dict:
  cookies = _carregar_cookies(environment)
  run_id = f"gal-{uuid.uuid4().hex[:12]}"
  buscou_em = datetime.now(UTC)
  municipios = {_normalizar(m) for m in C.MUNICIPIOS.value}

  itens: list[ItemLote] = []
  async with GalSessaoWeb(cookies=cookies) as sessao:
    linhas = await _varrer_grid(sessao, pagina_tamanho, limite_paginas)
    log(
      f"gal: {len(linhas)} laudo(s) no grid (antes do filtro de município)", level="info"
    )

    for linha in linhas:
      numero = str(linha.get("solicitacao") or "").strip()
      if not numero:
        continue
      if municipios and _normalizar(linha.get("munSolicitante") or "") not in municipios:
        continue
      try:
        pdf = await sessao.baixar_laudo_pdf([numero])
      except GalSessaoExpirada:
        raise
      except GalWebError as exc:
        log(f"gal: falha ao baixar laudo {numero}: {exc}", level="warning")
        continue
      itens.append(
        ItemLote(
          kind="laudo",
          source_ref=numero,
          conteudo={"grid": linha},
          blob_bytes=pdf,
          blob_content_type="application/pdf",
        )
      )

  run = RunMeta(
    robo="gal-flow", run_id=run_id, buscou_em=buscou_em, terminou_em=datetime.now(UTC)
  )
  resultado = enviar_lote(C.FONTE.value, run, itens, environment=environment)
  log(f"gal: {len(itens)} item(ns) enviado(s) ao COREVISA — {resultado}", level="info")
  return resultado


@task(name="gal-varrer-laudos")
def varrer_laudos(
  pagina_tamanho: int, limite_paginas: int | None, environment: str
) -> dict:
  return asyncio.run(_varrer(pagina_tamanho, limite_paginas, environment))
