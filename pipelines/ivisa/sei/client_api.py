# -*- coding: utf-8 -*-
"""Cliente do gateway "API SEI - Integra SUBG".

Base: https://sei.gateway.subgsms.rio
Autenticação por dois headers obrigatórios em todos os endpoints:
    X-System-Token  token do sistema consumidor (SUBG)
    X-Requester     login/matrícula/e-mail de quem solicitou

A API NÃO lista processos — todo endpoint exige `protocolo`. Serve para
enriquecer um protocolo já descoberto (discovery.py), nunca para descobrir.

Credenciais recebidas no construtor (buscadas do Infisical na task).
"""

from __future__ import annotations

from typing import Any

import httpx

from .constants import constants as C


class SeiApiError(RuntimeError):
  pass


class SeiApiNaoConfigurada(SeiApiError):
  pass


class SeiApiClient:
  def __init__(
    self, system_token: str, requester: str, base_url: str | None = None
  ) -> None:
    self.base_url = (base_url or C.API_BASE_URL.value).rstrip("/")
    self._token = system_token
    self._requester = requester
    self._client: httpx.AsyncClient | None = None

  @property
  def configurada(self) -> bool:
    return bool(self._token and self._requester)

  async def __aenter__(self) -> SeiApiClient:
    if not self.configurada:
      raise SeiApiNaoConfigurada(
        "SEI_API_SYSTEM_TOKEN/SEI_API_REQUESTER não configurados no Infisical /ivisa-rio."
      )
    self._client = httpx.AsyncClient(
      base_url=self.base_url,
      timeout=C.HTTP_TIMEOUT.value,
      headers={
        "X-System-Token": self._token or "",
        "X-Requester": self._requester or "",
        "Accept": "application/json",
      },
    )
    return self

  async def __aexit__(self, *_: object) -> None:
    if self._client:
      await self._client.aclose()
      self._client = None

  async def _get(self, caminho: str, params: dict[str, Any]) -> Any:
    assert self._client is not None
    resposta = await self._client.get(caminho, params=params)
    if resposta.status_code == 401:
      raise SeiApiError(f"401 do gateway SEI: {_detalhe(resposta)}")
    if resposta.status_code == 404:
      return None
    if resposta.status_code >= 400:
      raise SeiApiError(f"HTTP {resposta.status_code} em {caminho}: {_detalhe(resposta)}")
    return resposta.json()

  async def remessas(self, protocolo: str, id_unidade: str) -> list[dict[str, Any]]:
    dados = await self._get(
      "/api/v1/sei/remessas", {"protocolo": protocolo, "idUnidade": id_unidade}
    )
    return dados or []

  async def procedimento_simplificado(
    self, protocolo: str, id_unidade: str
  ) -> dict[str, Any] | None:
    return await self._get(
      "/api/v1/sei/procedimentos/simplificado",
      {"protocolo": protocolo, "idUnidade": id_unidade},
    )

  async def andamentos_todos(
    self, protocolo: str, id_unidade: str
  ) -> list[dict[str, Any]]:
    dados = await self._get(
      "/api/v1/sei/andamentos/todos", {"protocolo": protocolo, "idUnidade": id_unidade}
    )
    return dados or []

  async def unidades(self) -> list[dict[str, Any]]:
    dados = await self._get("/api/v1/sei/unidades", {})
    return dados or []


def _detalhe(resposta: httpx.Response) -> str:
  try:
    corpo = resposta.json()
    return str(corpo.get("detail") or corpo)[:300]
  except Exception:
    return resposta.text[:300]
