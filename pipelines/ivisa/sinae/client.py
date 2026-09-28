# -*- coding: utf-8 -*-
"""Client SOAP do WS Fazenda Estabelecimento (Prefeitura do Rio).

Sem scraping, sem sessão, sem login — o SOAP já é uma API estruturada,
autenticada por token fixo em cada chamada.

Achado (2026-09-24): o token só tem acesso às operações de LISTA. As de ficha
unitária por inscrição municipal (`BuscaInInscMunic`, Serviço 358/350) devolvem
Fault `SMF_358_006`/`SMF_350_007`. Por isso a busca é por CNPJ. Se a SMF liberar
esses Serviços, `busca_in_insc_munic` volta a ser a via direta.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Protocol

import zeep
import zeep.helpers
from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from zeep.exceptions import Fault
from zeep.transports import Transport

from .constants import constants as C


class FichaIndisponivel(RuntimeError):
  """`BuscaInInscMunic` recusou por falta de acesso do token a esse Serviço —
  diferente de "não encontrado" (resultado vazio, não Fault)."""

  def __init__(self, insc_munic: str, causa: Fault) -> None:
    super().__init__(
      f"sem acesso ao serviço de ficha por inscrição municipal ({insc_munic}): {causa}"
    )
    self.insc_munic = insc_munic
    self.causa = causa


class _Servico(Protocol):
  def BuscaInInscMunic(self, p_sToken: str, p_sInscMunic: str) -> Any: ...
  def BuscaListaAtividadeEconomicaInInscMunic(
    self, p_sToken: str, p_sInscMunic: str
  ) -> Any: ...
  def BuscaListaInCnpj(self, p_sToken: str, p_sCnpj: str) -> Any: ...
  def BuscaListaInscMunicInCnpj(self, p_sToken: str, p_sCnpj: str) -> Any: ...
  def HeartBeat(self) -> Any: ...


@lru_cache(maxsize=1)
def _zeep_client() -> zeep.Client:
  session = Session()
  retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
  session.mount("https://", HTTPAdapter(max_retries=retry))
  transport = Transport(session=session, timeout=30, operation_timeout=60)
  return zeep.Client(
    wsdl=C.WSDL_URL.value,
    transport=transport,
    settings=zeep.Settings(strict=False, xml_huge_tree=True),
  )


def _to_dict(obj: Any) -> Any:
  if obj is None:
    return None
  return zeep.helpers.serialize_object(obj, target_cls=dict)


class EstabelecimentoClient:
  def __init__(self, token: str, svc: _Servico | None = None) -> None:
    self.token = token
    self._svc = svc if svc is not None else _zeep_client().service

  def heartbeat(self) -> bool:
    return bool(self._svc.HeartBeat())

  def busca_in_insc_munic(self, insc_munic: str) -> dict[str, Any]:
    try:
      resultado = self._svc.BuscaInInscMunic(p_sToken=self.token, p_sInscMunic=insc_munic)
    except Fault as exc:
      raise FichaIndisponivel(insc_munic, exc) from exc
    return _to_dict(resultado) or {}

  def busca_lista_atividade_economica_in_insc_munic(
    self, insc_munic: str
  ) -> list[dict[str, Any]]:
    resultado = self._svc.BuscaListaAtividadeEconomicaInInscMunic(
      p_sToken=self.token, p_sInscMunic=insc_munic
    )
    return _to_dict(resultado) or []

  def busca_lista_in_cnpj(self, cnpj: str) -> list[dict[str, Any]]:
    resultado = self._svc.BuscaListaInCnpj(p_sToken=self.token, p_sCnpj=cnpj)
    return _to_dict(resultado) or []

  def busca_lista_insc_munic_in_cnpj(self, cnpj: str) -> list[str]:
    resultado = self._svc.BuscaListaInscMunicInCnpj(p_sToken=self.token, p_sCnpj=cnpj)
    return list(resultado) if resultado else []
