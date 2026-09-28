# -*- coding: utf-8 -*-
"""Sessão no Harpya (DATASUS/CGLAB) — login JSF + busca por código + busca por
período na tela de gestão.

Sem parsing de laudo: devolve o HTML cru (`laudo_html`) — quem extrai
ficha/ensaios/conclusão é o parser do COREVISA. Sem captcha: cada execução pode
logar de novo (o Harpya não mantém sessão entre chamadas).

Credenciais recebidas no construtor (buscadas do Infisical na task), não de
`settings` — diferente do ivisa-flows.
"""

from __future__ import annotations

import urllib.parse
from typing import Any

import httpx

from .constants import constants as C
from .parser import (
  decompor_codigo_harpya,
  extrair_html_ajax,
  extrair_row_count,
  extrair_viewstate,
  parse_gestao,
  parse_gestao_rows,
)

BASE_URL = C.BASE_URL.value
LOGIN_URL = f"{BASE_URL}/index.xhtml"
HOME_URL = f"{BASE_URL}/views/home.xhtml"
RELATORIO_URL = f"{BASE_URL}/resources/relatorios/relAnaliticoHtml.xhtml"
GESTAO_URL = f"{BASE_URL}/views/gestao/indexAmostraGestaoLocal.xhtml"

_HEADERS_BASE = {
  "User-Agent": "Mozilla/5.0",
  "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_PANELS_FIXED = {
  "panelDadosDaAmostra_collapsed": "false",
  "panelDadosDeDistribuicao_collapsed": "true",
  "panelDadosDeEnsaios_collapsed": "true",
  "panelDadosFechamentoAvaliacaoFinal_collapsed": "true",
  "panelSelecioneColunasSeremExibidasNaPesquisa_collapsed": "true",
}

_JSF_AJAX_BUSCAR = {
  "javax.faces.source": "btnBuscar",
  "javax.faces.partial.event": "click",
  "javax.faces.partial.execute": "btnBuscar frmPesquisarPorAmostraEnsaios",
  "javax.faces.partial.render": "frmPesquisarPorAmostraEnsaios messages",
  "javax.faces.behavior.event": "action",
  "javax.faces.partial.ajax": "true",
}

_TABELA_COLUMN_ORDER = ",".join(f"tabelaAmostras:j_idt{i}" for i in range(403, 582, 2))


class HarpyaError(RuntimeError):
  pass


class HarpyaNaoEncontrado(HarpyaError):
  """Número público não encontrado ou busca não retornou redirect."""


class HarpyaSessaoExpirada(HarpyaError):
  pass


class HarpyaSessao:
  """Sessão HTTP no Harpya. Usar como `async with` — uma sessão por operação."""

  def __init__(
    self, username: str, password: str, transport: httpx.AsyncBaseTransport | None = None
  ) -> None:
    self._username = username
    self._password = password
    self._transport = transport
    self._client: httpx.AsyncClient | None = None

  async def __aenter__(self) -> HarpyaSessao:
    self._client = httpx.AsyncClient(
      base_url=BASE_URL, timeout=30, transport=self._transport, headers=_HEADERS_BASE
    )
    return self

  async def __aexit__(self, *_exc: object) -> None:
    if self._client:
      await self._client.aclose()
      self._client = None

  async def login(self) -> None:
    assert self._client is not None
    if not self._username or not self._password:
      raise HarpyaError("HARPYA_USERNAME/HARPYA_PASSWORD não configurados.")

    resp = await self._client.get(LOGIN_URL, timeout=30)
    resp.raise_for_status()
    view_state = extrair_viewstate(resp.text)

    payload = {
      "loginForm": "loginForm",
      "username": self._username,
      "password": self._password,
      "btnEntrar": "Entrar",
      "javax.faces.ViewState": view_state,
    }
    resp_post = await self._client.post(
      LOGIN_URL,
      data=payload,
      headers={
        **_HEADERS_BASE,
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": LOGIN_URL,
        "Origin": BASE_URL,
      },
      follow_redirects=True,
      timeout=30,
    )
    resp_post.raise_for_status()
    if (
      "home.xhtml" not in str(resp_post.url) and "views/home.xhtml" not in resp_post.text
    ):
      raise HarpyaError("Login no Harpya não foi concluído com sucesso.")

  async def buscar_laudo_html(
    self, numero_publico: str, tipo: str = "INICIAL", ano: str = ""
  ) -> tuple[str, str]:
    """Busca um laudo pelo código público. Devolve `(laudo_html, pdf_url)`,
    cru. Levanta `HarpyaNaoEncontrado` se o código não existir."""
    assert self._client is not None
    componentes = decompor_codigo_harpya(numero_publico)
    ano_efetivo = ano or componentes["ano"]

    resp_home = await self._client.get(HOME_URL, timeout=30)
    resp_home.raise_for_status()
    view_state = extrair_viewstate(resp_home.text)
    cid = _extrair_cid(resp_home.text, str(resp_home.url))
    post_url = f"{HOME_URL}?cid={cid}" if cid else HOME_URL

    payload = {
      "formBusca": "formBusca",
      "formBusca:busca-numeracao": componentes["numeracao"],
      "formBusca:busca-tipo": tipo,
      "formBusca:busca-sequencial": componentes["sequencial"],
      "formBusca:busca-ano": ano_efetivo,
      "javax.faces.ViewState": view_state,
      "javax.faces.source": "formBusca:btnBuscaAmostra",
      "javax.faces.partial.event": "click",
      "javax.faces.partial.execute": "formBusca:btnBuscaAmostra formBusca",
      "javax.faces.partial.render": "formBusca",
      "javax.faces.behavior.event": "action",
      "javax.faces.partial.ajax": "true",
      "cid": cid or "",
    }
    resp_post = await self._client.post(
      post_url,
      data=payload,
      headers={
        **_HEADERS_BASE,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Faces-Request": "partial/ajax",
        "Referer": HOME_URL,
      },
      timeout=30,
    )
    resp_post.raise_for_status()

    from bs4 import BeautifulSoup

    soup_xml = BeautifulSoup(resp_post.text, "xml")
    redirect_tag = soup_xml.find("redirect")
    if not redirect_tag:
      raise HarpyaNaoEncontrado(
        f"Número público '{numero_publico}' não encontrado ou busca sem redirect."
      )

    redirect_url = str(redirect_tag.get("url", "") or "")
    params = urllib.parse.parse_qs(urllib.parse.urlparse(redirect_url).query)
    id_amostra = params.get("IdAmostra", params.get("idAmostra", [None]))[0]
    if not id_amostra:
      raise HarpyaError("idAmostra não encontrado na URL de redirect.")

    resp_relatorio = await self._client.get(
      RELATORIO_URL,
      params={"idAmostra": id_amostra},
      headers={**_HEADERS_BASE, "Referer": f"{HOME_URL}?cid=1"},
      timeout=30,
    )
    resp_relatorio.raise_for_status()
    if (
      "javax.faces.ViewState" in resp_relatorio.text
      and "username" in resp_relatorio.text
      and "password" in resp_relatorio.text
    ):
      raise HarpyaSessaoExpirada("Sessão expirou ao buscar relatório analítico.")

    pdf_url = f"{RELATORIO_URL}?idAmostra={id_amostra}"
    return resp_relatorio.text, pdf_url

  async def buscar_amostras_por_periodo(
    self,
    data_inicio: str | None = None,
    data_fim: str | None = None,
    tipo_data: str = "1",
    situacao_amostra: list[str] | None = None,
    page_size: str = "*",
  ) -> list[dict[str, Any]]:
    """Varre a tela de gestão por data (`DD/MM/AAAA`). `page_size="*"` traz
    tudo, paginando por dentro. Devolve linhas cruas."""
    assert self._client is not None
    resp_page = await self._client.get(GESTAO_URL, headers=_HEADERS_BASE, timeout=30)
    resp_page.raise_for_status()
    view_state = extrair_viewstate(resp_page.text)
    cid = _extrair_cid(resp_page.text, str(resp_page.url))
    gestao_url_cid = f"{GESTAO_URL}?cid={cid}" if cid else GESTAO_URL

    payload_simples: list[tuple[str, str]] = [
      ("frmPesquisarPorAmostraEnsaios", "frmPesquisarPorAmostraEnsaios"),
      ("cboTipoDeData", tipo_data),
      ("txtDataInicio", data_inicio or ""),
      ("txtDataFim", data_fim or ""),
      ("chkCheckBoxSelecionarTodosLab_input", "on"),
      ("javax.faces.ViewState", view_state),
      ("tabelaAmostras_rppDD", page_size),
      ("tabelaAmostras_first", "0"),
    ]
    payload_multi = [("selectSituacaoAmostra", v) for v in (situacao_amostra or [])]
    payload_multi += [("selectColunasDadosAmostra1", v) for v in ("CATPROD", "PRODUTO")]

    payload_final = (
      payload_simples
      + payload_multi
      + list(_PANELS_FIXED.items())
      + list(_JSF_AJAX_BUSCAR.items())
    )
    headers_ajax = {
      **_HEADERS_BASE,
      "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
      "Faces-Request": "partial/ajax",
      "Origin": BASE_URL,
      "Referer": GESTAO_URL,
    }
    resp = await self._client.post(
      gestao_url_cid,
      content=_form_encode(payload_final),
      headers=headers_ajax,
      timeout=60,
    )
    resp.raise_for_status()
    row_count = extrair_row_count(resp.text) or 0

    campos_form = (
      [
        (k, v)
        for k, v in payload_simples
        if k
        not in ("javax.faces.ViewState", "tabelaAmostras_rppDD", "tabelaAmostras_first")
      ]
      + payload_multi
      + list(_PANELS_FIXED.items())
    )

    async def _buscar_pagina(first: int, rows: int) -> list[dict[str, Any]]:
      payload_pag = [
        ("javax.faces.partial.ajax", "true"),
        ("javax.faces.source", "tabelaAmostras"),
        ("javax.faces.partial.execute", "tabelaAmostras"),
        ("javax.faces.partial.render", "tabelaAmostras"),
        ("tabelaAmostras", "tabelaAmostras"),
        ("tabelaAmostras_pagination", "true"),
        ("tabelaAmostras_first", str(first)),
        ("tabelaAmostras_rows", str(rows)),
        ("tabelaAmostras_skipChildren", "true"),
        ("tabelaAmostras_encodeFeature", "true"),
        *campos_form,
        ("tabelaAmostras_rppDD", str(rows)),
        ("tabelaAmostras_columnOrder", _TABELA_COLUMN_ORDER),
        ("javax.faces.ViewState", view_state),
      ]
      assert self._client is not None
      r = await self._client.post(
        gestao_url_cid,
        content=_form_encode(payload_pag),
        headers=headers_ajax,
        timeout=60,
      )
      r.raise_for_status()
      html = extrair_html_ajax(r.text, "tabelaAmostras")
      return parse_gestao_rows(html)

    if page_size != "*":
      html_primeira = extrair_html_ajax(resp.text, "frmPesquisarPorAmostraEnsaios")
      return parse_gestao(html_primeira)

    batch_size = 60
    todos_itens: list[dict[str, Any]] = []
    first = 0
    while first < row_count:
      itens_pagina = await _buscar_pagina(first, batch_size)
      if not itens_pagina:
        break
      todos_itens.extend(itens_pagina)
      first += batch_size
    return todos_itens


def _form_encode(pares: list[tuple[str, str]]) -> bytes:
  return urllib.parse.urlencode(pares).encode()


def _extrair_cid(html: str, url_final: str) -> str | None:
  from bs4 import BeautifulSoup

  soup = BeautifulSoup(html, "html.parser")
  cid_input = soup.find("input", {"name": "cid"})
  if cid_input:
    valor = cid_input.get("value")
    return str(valor) if valor else None
  parsed = urllib.parse.urlparse(url_final)
  return urllib.parse.parse_qs(parsed.query).get("cid", [None])[0]
