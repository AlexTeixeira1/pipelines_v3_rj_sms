# -*- coding: utf-8 -*-
"""Tasks do SEI — descoberta (web) + enriquecimento (gateway).

Descobre protocolo novo pela pesquisa autenticada (janela de SYNC_JANELA_DIAS),
enriquece cada um via gateway (remessas + procedimentos/simplificado) e posta
`kind="verificado"`. Este flow não decide `tem_ivisa` nem abre/fecha processo —
isso é o MapeadorSei no COREVISA.
"""

import asyncio
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from prefect import task

from pipelines.ivisa._shared.corevisa import ItemLote, RunMeta, enviar_lote
from pipelines.utils.infisical import get_secret
from pipelines.utils.logger import log

from .client_api import SeiApiClient
from .client_web import SeiSessaoWeb
from .constants import constants as C
from .discovery import DiscoveryWeb
from .tipos import ProcessoDescoberto

INFISICAL_PATH = "/ivisa-rio"


def _secret(nome: str, environment: str) -> str:
  return get_secret(path=INFISICAL_PATH, secret_name=nome, environment=environment)


async def _descobrir(
  usuario: str,
  senha: str,
  orgao: str,
  inicio: date,
  fim: date,
  orgaos: list[str],
  max_paginas: int,
) -> list[ProcessoDescoberto]:
  descobertos: list[ProcessoDescoberto] = []
  async with SeiSessaoWeb(usuario=usuario, senha=senha, orgao=orgao) as sessao_web:
    descoberta = DiscoveryWeb(
      sessao_web,
      orgaos=orgaos,
      max_paginas=max_paginas,
      restringir_orgao=C.RESTRINGIR_ORGAO.value,
    )
    async for item in descoberta.listar_protocolos(inicio, fim):
      descobertos.append(item)
  return descobertos


async def _enriquecer(
  api: SeiApiClient, protocolo: str, id_unidade: str
) -> dict[str, Any] | None:
  simplificado = await api.procedimento_simplificado(protocolo, id_unidade)
  if simplificado is None:
    return None
  remessas = await api.remessas(protocolo, id_unidade)
  return {"simplificado": simplificado, "remessas": remessas}


async def _varrer(janela_dias: int, max_paginas: int, environment: str) -> dict:
  usuario = _secret(C.SECRET_USUARIO.value, environment)
  senha = _secret(C.SECRET_SENHA.value, environment)
  orgao = _secret(C.SECRET_ORGAO.value, environment)
  system_token = _secret(C.SECRET_API_SYSTEM_TOKEN.value, environment)
  requester = _secret(C.SECRET_API_REQUESTER.value, environment)
  id_unidade = _secret(C.SECRET_API_ID_UNIDADE.value, environment)

  run_id = f"sei-{uuid.uuid4().hex[:12]}"
  buscou_em = datetime.now(UTC)
  fim = date.today()
  inicio = fim - timedelta(days=janela_dias)
  orgaos = [o.strip() for o in C.SYNC_ORGAOS.value.split(",") if o.strip()]

  descobertos = await _descobrir(usuario, senha, orgao, inicio, fim, orgaos, max_paginas)
  log(
    f"sei: {len(descobertos)} protocolo(s) descoberto(s) entre {inicio} e {fim}",
    level="info",
  )

  itens: list[ItemLote] = []
  if descobertos:
    async with SeiApiClient(system_token=system_token, requester=requester) as api:
      for item in descobertos:
        enriquecido = await _enriquecer(api, item.protocolo, id_unidade)
        if enriquecido is None:
          log(
            f"sei: protocolo {item.protocolo} não encontrado no gateway", level="warning"
          )
          continue
        itens.append(
          ItemLote(kind="verificado", source_ref=item.protocolo, conteudo=enriquecido)
        )

  run = RunMeta(
    robo="sei-flow",
    run_id=run_id,
    buscou_em=buscou_em,
    terminou_em=datetime.now(UTC),
    janela_inicio=datetime.combine(inicio, datetime.min.time(), tzinfo=UTC),
    janela_fim=datetime.combine(fim, datetime.min.time(), tzinfo=UTC),
  )
  resultado = enviar_lote(C.FONTE.value, run, itens, environment=environment)
  log(f"sei: {len(itens)} item(ns) enviado(s) ao COREVISA — {resultado}", level="info")
  return resultado


@task(name="sei-descobrir-e-enriquecer")
def descobrir_e_enriquecer(janela_dias: int, max_paginas: int, environment: str) -> dict:
  return asyncio.run(_varrer(janela_dias, max_paginas, environment))
