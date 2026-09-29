# -*- coding: utf-8 -*-
"""Sessão autenticada na interface web do SEI.

Dois fixes identificados testando contra a instância real (2026-09):
1. `selData` padrão vira `"G"` (data do processo), não `"I"`.
2. `chkSinRestringirOrgao="S"` precisa ser mandado explicitamente.

Scraping é a única via de descoberta: a API do gateway não lista processos e a
pesquisa pública tem captcha. A pesquisa autenticada não tem captcha.

Credenciais recebidas no construtor (buscadas do Infisical na task), não de
`settings`.
"""

from __future__ import annotations

import asyncio
import re
from datetime import date

import httpx
from bs4 import BeautifulSoup

from pipelines.utils.logger import log

from .constants import constants as C
from .parser import sessao_expirada

CAMINHO_LOGIN = "/sei/controlador.php?acao=usuario_sistema_logar"
ACAO_PESQUISA = "protocolo_pesquisar"


class SeiWebError(RuntimeError):
  pass


class SeiCredenciaisAusentes(SeiWebError):
  pass


class SeiSessaoWeb:
  """Sessão HTTP autenticada. Usar como async context manager."""

  def __init__(
    self,
    usuario: str,
    senha: str,
    orgao: str = "",
    base_url: str | None = None,
    delay_ms: int | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
  ) -> None:
    self.base_url = (base_url or C.BASE_URL.value).rstrip("/")
    self._usuario = usuario
    self._senha = senha
    self._orgao = orgao
    self._delay = (delay_ms if delay_ms is not None else C.SYNC_DELAY_MS.value) / 1000
    self._transport = transport
    self._client: httpx.AsyncClient | None = None
    self._logado = False
    self._lock = asyncio.Lock()
    self._html_inicial: str = ""
    self._url_inicial: str = self.base_url

  async def __aenter__(self) -> SeiSessaoWeb:
    if not self._usuario or not self._senha:
      raise SeiCredenciaisAusentes(
        "SEI_USUARIO/SEI_SENHA não configurados no Infisical /ivisa-rio."
      )
    self._client = httpx.AsyncClient(
      base_url=self.base_url,
      timeout=C.HTTP_TIMEOUT.value,
      follow_redirects=True,
      transport=self._transport,
      headers={
        "User-Agent": "ivisa-flows/1.0 (integracao institucional IVISA-RIO)",
        "Accept-Language": "pt-BR,pt;q=0.9",
      },
    )
    return self

  async def __aexit__(self, *_: object) -> None:
    if self._client:
      await self._client.aclose()
      self._client = None
    self._logado = False

  async def _request(self, metodo: str, url: str, **kwargs: object) -> httpx.Response:
    assert self._client is not None
    async with self._lock:
      ultima_excecao: Exception | None = None
      for tentativa in range(3):
        if self._delay:
          await asyncio.sleep(self._delay * (1 + tentativa))
        try:
          resposta = await self._client.request(metodo, url, **kwargs)  # type: ignore[arg-type]
        except httpx.HTTPError as exc:
          ultima_excecao = exc
          log(
            f"SEI {metodo} {url} falhou (tentativa {tentativa + 1}): {exc}",
            level="warning",
          )
          continue
        if resposta.status_code >= 500:
          ultima_excecao = SeiWebError(f"HTTP {resposta.status_code} em {url}")
          log(
            f"SEI devolveu {resposta.status_code} em {url} (tentativa {tentativa + 1})",
            level="warning",
          )
          continue
        if resposta.status_code >= 400:
          log(f"SEI devolveu {resposta.status_code} em {resposta.url}", level="warning")
        return resposta
      raise SeiWebError(
        f"SEI não respondeu após 3 tentativas em {url}"
      ) from ultima_excecao

  async def login(self) -> None:
    resposta = await self._request("GET", CAMINHO_LOGIN)
    soup = BeautifulSoup(resposta.text, "html.parser")
    formulario = soup.find("form", id="frmLogin") or soup.find("form")
    if formulario is None:
      raise SeiWebError("Tela de login do SEI sem formulário - marcação mudou.")

    dados = _campos_ocultos(formulario)
    dados.update(
      {
        "txtUsuario": self._usuario or "",
        "pwdSenha": self._senha or "",
        "hdnAcao": "2",
        "sbmAcessar": "Acessar",
      }
    )
    orgao = _resolver_orgao(formulario, self._orgao)
    if orgao is not None:
      dados["selOrgao"] = orgao

    destino = str(resposta.url.join(formulario.get("action") or ""))
    resposta = await self._request("POST", destino, data=dados)

    if not _autenticado(resposta):
      raise SeiWebError(
        "Login no SEI recusado. Confira SEI_USUARIO, SEI_SENHA e SEI_ORGAO "
        f"(SEI_ORGAO é o valor numérico do <select>, ex.: 16 = SMS). "
        f"Resposta HTTP {resposta.status_code} em {resposta.url}."
      )
    self._logado = True
    self._html_inicial = resposta.text
    self._url_inicial = str(resposta.url)
    log(f"Sessão SEI aberta para {self._usuario}", level="info")

  async def garantir_login(self) -> None:
    if not self._logado:
      await self.login()

  async def get_html(self, url: str) -> str:
    await self.garantir_login()
    resposta = await self._request("GET", url)
    if sessao_expirada(resposta.text):
      log("Sessão SEI expirou; refazendo login", level="info")
      self._logado = False
      await self.garantir_login()
      resposta = await self._request("GET", url)
    return resposta.text

  async def abrir_pesquisa(self) -> tuple[str, dict[str, str], str]:
    await self.garantir_login()
    link = _link_por_acao(self._html_inicial, ACAO_PESQUISA)
    if not link:
      self._logado = False
      await self.garantir_login()
      link = _link_por_acao(self._html_inicial, ACAO_PESQUISA)
    if not link:
      raise SeiWebError(
        "Link de Pesquisa não encontrado no menu do SEI. O usuário tem permissão "
        "de pesquisa nesta unidade?"
      )

    destino = str(httpx.URL(self._url_inicial).join(link))
    resposta = await self._request("GET", destino)
    if sessao_expirada(resposta.text):
      self._logado = False
      await self.garantir_login()
      link = _link_por_acao(self._html_inicial, ACAO_PESQUISA) or link
      resposta = await self._request("GET", str(httpx.URL(self._url_inicial).join(link)))

    soup = BeautifulSoup(resposta.text, "html.parser")
    formulario = next(
      (f for f in soup.find_all("form") if f.find(attrs={"name": "txtDataInicio"})), None
    )
    formulario = formulario or soup.find("form", id="frmProtocoloPesquisar")
    if formulario is None:
      raise SeiWebError(
        f"Tela de pesquisa do SEI sem formulário (HTTP {resposta.status_code} em "
        f"{resposta.url}) - endpoint ou marcação mudou."
      )
    acao = str(resposta.url.join(formulario.get("action") or ""))
    return acao, _campos_ocultos(formulario), resposta.text

  async def pesquisar_periodo(
    self,
    inicio: date,
    fim: date,
    orgaos: list[str] | None = None,
    offset: int = 0,
    id_unidade: str | None = None,
    considerar_tramitacao: bool = False,
    tipo_data: str = "G",
    restringir_orgao: bool = True,
  ) -> str:
    acao, ocultos, _ = await self.abrir_pesquisa()
    dados: dict[str, object] = dict(ocultos)
    dados.update(
      {
        "rdoPesquisarEm": "P",
        "selData": tipo_data,
        "txtDataInicio": inicio.strftime("%d/%m/%Y"),
        "txtDataFim": fim.strftime("%d/%m/%Y"),
        "hdnInicio": str(offset),
        "sbmPesquisar": "Pesquisar",
      }
    )
    if orgaos:
      dados["selOrgaoPesquisa[]"] = orgaos
    if restringir_orgao:
      dados["chkSinRestringirOrgao"] = "S"
    if id_unidade:
      dados["hdnIdUnidade"] = id_unidade
    if considerar_tramitacao:
      dados["chkSinTramitacao"] = "S"

    resposta = await self._request("POST", acao, data=dados)
    if sessao_expirada(resposta.text):
      self._logado = False
      await self.garantir_login()
      return await self.pesquisar_periodo(
        inicio,
        fim,
        orgaos,
        offset,
        id_unidade,
        considerar_tramitacao,
        tipo_data,
        restringir_orgao,
      )
    return resposta.text


def _campos_ocultos(formulario: object) -> dict[str, str]:
  dados: dict[str, str] = {}
  for campo in formulario.find_all("input"):  # type: ignore[attr-defined]
    nome = campo.get("name")
    if not nome:
      continue
    if (campo.get("type") or "text").lower() == "hidden":
      dados[nome] = campo.get("value") or ""
  return dados


def _resolver_orgao(formulario: object, configurado: str | None) -> str | None:
  if not configurado:
    return None
  alvo = configurado.strip()
  if alvo.isdigit():
    return alvo

  select = formulario.find("select", attrs={"name": "selOrgao"})  # type: ignore[attr-defined]
  if select is None:
    return alvo
  for opcao in select.find_all("option"):
    rotulo = re.sub(r"\s+", "", opcao.get_text() or "")
    if rotulo.upper() == alvo.upper():
      valor = opcao.get("value")
      log(f"SEI_ORGAO '{alvo}' resolvido para selOrgao={valor}", level="info")
      return valor
  raise SeiWebError(
    f"SEI_ORGAO='{alvo}' não corresponde a nenhum órgão da tela de login. "
    "Use o valor numérico do <select> (ex.: 16 = SMS) ou a sigla exata."
  )


def _link_por_acao(html: str, acao: str) -> str | None:
  if not html:
    return None
  soup = BeautifulSoup(html, "html.parser")
  for ancora in soup.find_all("a", href=True):
    href = ancora["href"]
    if f"acao={acao}" in href and "infra_hash=" in href:
      return href
  return None


def _autenticado(resposta: httpx.Response) -> bool:
  if resposta.status_code >= 400:
    return False
  corpo = resposta.text or ""
  if re.search(r'name="pwdSenha"', corpo, re.IGNORECASE):
    return False
  if "infra_hash" in corpo:
    return True
  return "controlador.php?acao=" in corpo
