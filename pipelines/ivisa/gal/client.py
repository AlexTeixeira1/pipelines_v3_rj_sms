# -*- coding: utf-8 -*-
"""Sessão autenticada no GAL (instância RJ, módulo Ambiental).

Scraping/sessão. O login tem CAPTCHA por acesso, então a sessão NÃO é aberta
aqui — o operador resolve o captcha localmente e o cookie de sessão (PHPSESSID)
é injetado a partir do Infisical (recebido no construtor como lista de cookies).
Quando o cookie expira, o GAL devolve HTML no lugar do JSON/PDF → vira
`GalSessaoExpirada`, e cabe ao operador renovar o secret no Infisical.

Requisições serializadas com intervalo. Sem paralelismo.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from .constants import constants as C

_UA_BROWSER = (
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_AJAX = {"X-Requested-With": "XMLHttpRequest"}
ROTA_LISTA_FINAIS = "/amb/laudos/lista-finais/"
ROTA_IMPRIMIR = "/amb/laudos/imprimir-fechadas/"


class GalWebError(RuntimeError):
  pass


class GalSessaoExpirada(GalWebError):
  """O cookie de sessão não vale mais — o operador precisa renovar o secret
  GAL_SESSAO_COOKIE no Infisical (resolvendo o captcha localmente)."""


def _parece_html(texto: str) -> bool:
  t = (texto or "").lstrip().lower()
  return t.startswith("<?xml") or t.startswith("<!doctype") or t.startswith("<html")


class GalSessaoWeb:
  """Sessão HTTP que reusa o cookie vindo do Infisical. Usar como `async with`.

  `cookies` é a lista `[{name, value, domain?, path?}, ...]` extraída do JSON
  gravado pelo operador (o mesmo shape do login_manual).
  """

  def __init__(
    self,
    cookies: list[dict[str, Any]],
    base_url: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
  ) -> None:
    self.base_url = (base_url or C.BASE_URL.value).rstrip("/")
    self._cookies = cookies
    self._delay = C.SYNC_DELAY_MS.value / 1000
    self._verify = C.TLS_VERIFY.value
    self._transport = transport
    self._client: httpx.AsyncClient | None = None
    self._lock = asyncio.Lock()

  async def __aenter__(self) -> GalSessaoWeb:
    self._client = httpx.AsyncClient(
      base_url=self.base_url,
      timeout=C.HTTP_TIMEOUT.value,
      follow_redirects=True,
      verify=self._verify,
      transport=self._transport,
      headers={"User-Agent": _UA_BROWSER, "Accept-Language": "pt-BR,pt;q=0.9"},
    )
    self._injetar_cookies()
    return self

  async def __aexit__(self, *_exc: object) -> None:
    if self._client:
      await self._client.aclose()
      self._client = None

  def _injetar_cookies(self) -> None:
    assert self._client is not None
    host = httpx.URL(self.base_url).host
    for item in self._cookies:
      self._client.cookies.set(
        item["name"],
        item["value"],
        domain=item.get("domain") or host,
        path=item.get("path", "/"),
      )

  def tem_cookie(self) -> bool:
    assert self._client is not None
    return bool(self._client.cookies)

  async def _request(self, metodo: str, url: str, **kwargs: object) -> httpx.Response:
    assert self._client is not None
    async with self._lock:
      if self._delay:
        await asyncio.sleep(self._delay)
      try:
        resp = await self._client.request(metodo, url, **kwargs)  # type: ignore[arg-type]
      except httpx.HTTPError as exc:
        raise GalWebError(f"{metodo} {url}: {exc.__class__.__name__}: {exc}") from exc
    if resp.status_code >= 500:
      raise GalWebError(f"{metodo} {url}: HTTP {resp.status_code}")
    return resp

  def garantir_sessao(self) -> None:
    if not self.tem_cookie():
      raise GalSessaoExpirada(
        "Sem cookie de sessão. Renove o secret GAL_SESSAO_COOKIE no "
        "Infisical /ivisa-rio (resolva o captcha localmente)."
      )

  async def lista_finais(
    self, numero: str | None = None, start: int = 0, limit: int = 20
  ) -> tuple[list[dict], int]:
    self.garantir_sessao()
    data: dict[str, object] = {
      "start": start,
      "limit": limit,
      "method": "post",
      "sort": "solicitacao",
      "dir": "DESC",
    }
    if numero:
      data["filter[0][field]"] = "solicitacao"
      data["filter[0][data][type]"] = "string"
      data["filter[0][data][value]"] = numero
    resp = await self._request("POST", ROTA_LISTA_FINAIS, data=data, headers=_AJAX)
    if _parece_html(resp.text):
      raise GalSessaoExpirada("lista-finais devolveu HTML — sessão expirou.")
    try:
      corpo = resp.json()
    except ValueError as exc:
      raise GalWebError(f"lista-finais: resposta não-JSON: {resp.text[:120]!r}") from exc
    if not isinstance(corpo, dict) or "dados" not in corpo:
      raise GalWebError(f"lista-finais: shape inesperado: {str(corpo)[:200]}")
    return list(corpo.get("dados") or []), int(corpo.get("total") or 0)

  async def baixar_laudo_pdf(self, numeros: list[str]) -> bytes:
    """PDF do(s) laudo(s). EFEITO COLATERAL no GAL: marca impressoFinal=1."""
    self.garantir_sessao()
    resp = await self._request(
      "GET", ROTA_IMPRIMIR, params={"solicitacoes": json.dumps(list(numeros))}
    )
    ct = resp.headers.get("content-type", "")
    if "pdf" in ct or resp.content[:4] == b"%PDF":
      return resp.content
    if _parece_html(resp.text):
      raise GalSessaoExpirada(
        "imprimir-fechadas devolveu HTML — sessão expirou ou número inválido."
      )
    raise GalWebError(
      f"imprimir-fechadas: content-type {ct!r}, {len(resp.content)} bytes"
    )
