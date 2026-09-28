# -*- coding: utf-8 -*-
"""Cliente da API pública do e-SISBI (sistemasweb.agricultura.gov.br/sisbi_api).

Mesma API REST que a SPA do "Acesso público" do SGSI consome. Sem token, sem
cookie. A única exigência é um User-Agent de browser: com UA não-browser o
servidor devolve o shell da SPA ("SGSI") em vez do JSON.

Paginação: `?page=<1..N>&count=<tam>` — os dois juntos. Sem `count`, `page` é
ignorado e a lista trava em 10. `count` até 200 funciona; acima fica instável.
"""

from __future__ import annotations

from typing import Any

import httpx

from .constants import constants as C


class EsisbiIndisponivel(RuntimeError):
  """Falha de rede/HTTP, ou resposta que não é JSON (SPA stub)."""


def _limpar_filtros(filtros: dict[str, Any]) -> dict[str, str]:
  saida: dict[str, str] = {}
  for chave, valor in filtros.items():
    if valor is None or valor == "":
      continue
    saida[chave] = (
      "true" if valor is True else ("false" if valor is False else str(valor))
    )
  return saida


class EsisbiApiClient:
  """Cliente HTTP com um `httpx.AsyncClient` reaproveitado no ciclo inteiro."""

  def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
    self._base = C.API_BASE_URL.value.rstrip("/")
    self._cliente = httpx.AsyncClient(
      timeout=C.HTTP_TIMEOUT.value,
      follow_redirects=True,
      headers=C.HEADERS.value,
      transport=transport,
    )

  async def __aenter__(self) -> EsisbiApiClient:
    return self

  async def __aexit__(self, *_exc: object) -> None:
    await self.aclose()

  async def aclose(self) -> None:
    await self._cliente.aclose()

  async def _get(self, caminho: str, params: dict[str, str] | None = None) -> Any:
    url = f"{self._base}/{caminho.lstrip('/')}"
    try:
      resp = await self._cliente.get(url, params=params)
    except httpx.HTTPError as exc:
      raise EsisbiIndisponivel(f"{caminho}: {exc.__class__.__name__}: {exc}") from exc
    if resp.status_code != 200:
      raise EsisbiIndisponivel(f"{caminho}: HTTP {resp.status_code} em {resp.url}")
    try:
      return resp.json()
    except ValueError as exc:
      trecho = resp.text[:80].replace("\n", " ")
      raise EsisbiIndisponivel(
        f"{caminho}: resposta não-JSON (UA bloqueada?): {trecho!r}"
      ) from exc

  async def contar(self, recurso: str, **filtros: Any) -> int:
    dado = await self._get(f"{recurso}/count", _limpar_filtros(filtros))
    try:
      return int(dado)
    except (TypeError, ValueError) as exc:
      raise EsisbiIndisponivel(
        f"{recurso}/count: esperado inteiro, veio {dado!r}"
      ) from exc

  async def listar(self, recurso: str, **filtros: Any) -> list[dict[str, Any]]:
    dado = await self._get(recurso, _limpar_filtros(filtros))
    if not isinstance(dado, list):
      raise EsisbiIndisponivel(f"{recurso}: esperada lista, veio {type(dado).__name__}")
    return dado

  async def obter(self, recurso: str, ident: int | str) -> dict[str, Any]:
    dado = await self._get(f"{recurso}/{ident}")
    if not isinstance(dado, dict):
      raise EsisbiIndisponivel(
        f"{recurso}/{ident}: esperado objeto, veio {type(dado).__name__}"
      )
    return dado
