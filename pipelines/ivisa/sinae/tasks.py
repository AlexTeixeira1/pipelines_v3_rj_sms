# -*- coding: utf-8 -*-
"""Tasks do SINAE — drena `/solicitacoes` (sem varredura).

O SOAP não tem "listar tudo": o flow só responde ao que foi pedido via
`POST /v1/ingestao/sinae/solicitar`. Busca por CNPJ (14 dígitos); inscrição
municipal isolada não tem ficha disponível com o token atual (ver client.py).
"""

import re
import uuid
from datetime import UTC, datetime

from prefect import task

from pipelines.ivisa._shared.corevisa import (
  ItemLote,
  RunMeta,
  concluir_solicitacao,
  enviar_lote,
  listar_solicitacoes,
)
from pipelines.utils.infisical import get_secret
from pipelines.utils.logger import log

from .client import EstabelecimentoClient, FichaIndisponivel
from .constants import constants as C

INFISICAL_PATH = "/ivisa-rio"


def _tipo_identificador(identificador: str) -> str:
  return "cnpj" if len(re.sub(r"\D", "", identificador)) == 14 else "insc_munic"


def _sem_cadastro(identificador: str, tipo: str) -> ItemLote:
  return ItemLote(
    kind="sem_cadastro",
    source_ref=identificador,
    conteudo={"identificador": identificador, "tipo_identificador": tipo},
  )


def _cadastro(
  identificador: str, tipo: str, ficha: dict, atividades: list[dict]
) -> ItemLote:
  return ItemLote(
    kind="cadastro",
    source_ref=identificador,
    conteudo={
      "identificador": identificador,
      "tipo_identificador": tipo,
      "ficha": ficha,
      "atividades": atividades,
    },
  )


def _buscar_por_cnpj(cliente: EstabelecimentoClient, cnpj: str) -> ItemLote:
  fichas = cliente.busca_lista_in_cnpj(cnpj)
  if not fichas:
    return _sem_cadastro(cnpj, "cnpj")
  atividades: list[dict] = []
  vistos: set[str] = set()
  for insc_munic in cliente.busca_lista_insc_munic_in_cnpj(cnpj):
    if insc_munic in vistos:
      continue
    vistos.add(insc_munic)
    atividades.extend(cliente.busca_lista_atividade_economica_in_insc_munic(insc_munic))
  return _cadastro(cnpj, "cnpj", fichas[0], atividades)


def _buscar_por_insc_munic(
  cliente: EstabelecimentoClient, insc_munic: str
) -> ItemLote | None:
  """`None` = não dá pra dizer nada agora (sem acesso ao serviço de ficha
  unitária) — melhor não emitir item do que mandar sem_cadastro à toa."""
  try:
    ficha = cliente.busca_in_insc_munic(insc_munic)
  except FichaIndisponivel:
    log(
      f"sinae: sem acesso ao serviço de ficha por inscrição municipal ({insc_munic}) "
      "— peça o CNPJ ao consumidor, ou solicite à SMF acesso ao Serviço 358/350.",
      level="warning",
    )
    return None
  if not ficha:
    return _sem_cadastro(insc_munic, "insc_munic")
  atividades = cliente.busca_lista_atividade_economica_in_insc_munic(insc_munic)
  return _cadastro(insc_munic, "insc_munic", ficha, atividades)


def _buscar_cadastro(
  cliente: EstabelecimentoClient, identificador: str
) -> ItemLote | None:
  if _tipo_identificador(identificador) == "cnpj":
    return _buscar_por_cnpj(cliente, identificador)
  return _buscar_por_insc_munic(cliente, identificador)


@task(name="sinae-drenar-solicitacoes")
def drenar_solicitacoes(environment: str) -> dict:
  solicitacoes = listar_solicitacoes(C.FONTE.value, environment=environment)
  if not solicitacoes:
    log("sinae: nenhuma solicitação pendente", level="info")
    return {"status": "vazio", "itens": 0}

  token = get_secret(
    path=INFISICAL_PATH, secret_name=C.SECRET_TOKEN.value, environment=environment
  )
  run_id = f"sinae-{uuid.uuid4().hex[:12]}"
  buscou_em = datetime.now(UTC)
  cliente = EstabelecimentoClient(token=token)

  itens: list[ItemLote] = []
  for solicitacao in solicitacoes:
    for identificador in solicitacao.get("ids") or []:
      try:
        item = _buscar_cadastro(cliente, identificador)
      except Exception as exc:  # noqa: BLE001 — segue pros próximos ids
        log(f"sinae: falha ao buscar {identificador}: {exc}", level="warning")
        continue
      if item is not None:
        itens.append(item)
    concluir_solicitacao(C.FONTE.value, solicitacao["id"], environment=environment)

  run = RunMeta(
    robo="sinae-flow", run_id=run_id, buscou_em=buscou_em, terminou_em=datetime.now(UTC)
  )
  resultado = enviar_lote(C.FONTE.value, run, itens, environment=environment)
  log(f"sinae: {len(itens)} item(ns) enviado(s) ao COREVISA — {resultado}", level="info")
  return resultado
