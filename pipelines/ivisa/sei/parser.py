"""HTML do SEI -> dataclasses. Sem rede, sem estado, sem I/O.

Portado de `adm-predial` (`app/services/sei/parser.py`) — só o que a
**descoberta** (fase 1, nunca portada pro corevisa — ver `docs/fontes/sei.md`
lá) usa: extrair protocolos da grade de pesquisa e decidir paginação/sessão
expirada. `parse_andamentos` (tela de andamento, usada por um flow separado
de histórico) não foi portado ainda.

Duas estratégias por página, nesta ordem:

1. Grade `infraTable` / `pesquisaResultado`, a marcação padrão do framework
   Infra usado pelo SEI.
2. Varredura por padrão: acha os protocolos por regex e lê o contexto ao redor.

A estratégia 2 existe porque o SEI é atualizado sem aviso e uma mudança de
classe CSS não deve zerar a coleta silenciosamente.
"""

from __future__ import annotations

import re
from datetime import datetime

from bs4 import BeautifulSoup

from .tipos import ProcessoDescoberto

# Formato de número de processo.
#   000990.005328/2026-54   <- confirmado contra a instância da Prefeitura do Rio
# O bloco antes do ponto tem 6 dígitos aqui; outras instâncias do SEI usam 5.
# A faixa {5,7} cobre as duas sem afrouxar o resto do padrão.
RE_PROTOCOLO = re.compile(r"\b\d{5,7}\.\d{6,7}/\d{4}-\d{2}\b")
RE_DATA = re.compile(r"\b(\d{2}/\d{2}/\d{4})(?:\s+(\d{2}:\d{2}(?::\d{2})?))?")
# Sigla de unidade: S/IVISA-RIO/CAD/GIL, S/SMS, CVL/SUBG/CGM ...
# O primeiro token pode ter UMA letra só ("S/IVISA-RIO"), daí o {0,20}.
# Tokens soltos de 1-2 letras são descartados depois, em `_primeira_sigla`.
RE_SIGLA = re.compile(r"\b[A-Z][A-Z0-9\-]{0,20}(?:/[A-Z0-9\-]{1,20}){0,6}\b")

RESULTADOS_POR_PAGINA = 10

RE_EXIBINDO = re.compile(
  r"Exibindo\s+([\d.]+)\s*-\s*([\d.]+)\s+de\s+([\d.]+)", re.IGNORECASE
)
RE_NAVEGAR = re.compile(r"navegar\(\s*'(\d+)'\s*\)")


def _texto(no: object) -> str:
  return re.sub(r"\s+", " ", no.get_text(" ", strip=True)) if no else ""  # type: ignore[attr-defined]


def parse_data(valor: str | None) -> datetime | None:
  """dd/mm/aaaa [hh:mm[:ss]] -> datetime naive (horário local de Brasília)."""
  if not valor:
    return None
  achado = RE_DATA.search(valor)
  if not achado:
    return None
  data, hora = achado.group(1), achado.group(2)
  for formato in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y"):
    try:
      return datetime.strptime(f"{data} {hora}".strip() if hora else data, formato)
    except ValueError:
      continue
  return None


def _tabelas_infra(soup: BeautifulSoup) -> list:
  tabelas = soup.find_all("table", class_=lambda c: bool(c) and "infraTable" in c)
  return tabelas or soup.find_all("table")


def extrair_protocolo(texto: str) -> str | None:
  achado = RE_PROTOCOLO.search(texto or "")
  return achado.group(0).upper() if achado else None


def total_resultados(html: str) -> int | None:
  """Lê o contador 'Exibindo 1 - 10 de 1.537' e devolve 1537.

  Com uma única página de resultados o SEI não desenha essa barra; nesse
  caso o total é a própria contagem de registros da página."""
  achado = RE_EXIBINDO.search(html or "")
  if achado:
    return int(achado.group(3).replace(".", "").replace(",", ""))
  registros = len(parse_resultados_pesquisa(html))
  return registros if registros else None


def offsets_disponiveis(html: str) -> list[int]:
  """Offsets de paginação. O SEI navega por `javascript:navegar('10')`."""
  return sorted({int(m.group(1)) for m in RE_NAVEGAR.finditer(html or "")})


def proximo_offset(html: str, offset_atual: int) -> int | None:
  for valor in offsets_disponiveis(html):
    if valor > offset_atual:
      return valor
  return None


def parse_resultados_pesquisa(html: str) -> list[ProcessoDescoberto]:
  """Lê a grade de resultados da pesquisa do SEI.

  A tela autenticada NÃO usa uma linha por registro. Cada resultado ocupa um
  bloco de `<tr>`s dentro de `table.pesquisaResultado`:

      tr.pesquisaTituloRegistro  -> <span>tipo</span> + a.protocoloNormal
      tr > td.pesquisaSnippet    -> trecho do conteúdo
      tr > td.pesquisaMetatag    -> Unidade / Usuário / Inclusão

  Ler `<tr>` isoladamente (como faz o fallback genérico) pega o protocolo mas
  perde data e unidade, porque elas vivem em outra linha do mesmo bloco.
  """
  soup = BeautifulSoup(html or "", "html.parser")

  estruturados = _parse_grade_pesquisa(soup)
  if estruturados:
    return estruturados

  encontrados: dict[str, ProcessoDescoberto] = {}

  for tabela in _tabelas_infra(soup):
    for linha in tabela.find_all("tr"):
      celulas = linha.find_all(["td", "th"])
      if not celulas:
        continue
      texto_linha = _texto(linha)
      protocolo = extrair_protocolo(texto_linha)
      if not protocolo or protocolo in encontrados:
        continue
      link = linha.find("a", href=True)
      encontrados[protocolo] = ProcessoDescoberto(
        protocolo=protocolo,
        data_autuacao=parse_data(texto_linha),
        unidade_geradora_sigla=_primeira_sigla(texto_linha, ignorar=protocolo),
        especificacao=_texto(celulas[-1])[:2000] or None,
        link_acesso=link["href"] if link else None,
      )

  if encontrados:
    return list(encontrados.values())

  # Fallback: o SEI mudou a marcação da grade. Acha os protocolos onde estiverem.
  texto_pagina = _texto(soup)
  for achado in RE_PROTOCOLO.finditer(texto_pagina):
    protocolo = achado.group(0).upper()
    if protocolo in encontrados:
      continue
    janela = texto_pagina[achado.start() : achado.end() + 300]
    encontrados[protocolo] = ProcessoDescoberto(
      protocolo=protocolo,
      data_autuacao=parse_data(janela),
      unidade_geradora_sigla=_primeira_sigla(janela, ignorar=protocolo),
    )
  return list(encontrados.values())


def _tem_classe(no: object, classe: str) -> bool:
  return classe in (no.get("class") or [])  # type: ignore[attr-defined]


def _parse_grade_pesquisa(soup: BeautifulSoup) -> list[ProcessoDescoberto]:
  """Caminho específico da grade `pesquisaResultado` da tela autenticada."""
  titulos = soup.find_all("tr", class_="pesquisaTituloRegistro")
  if not titulos:
    return []

  resultados: dict[str, ProcessoDescoberto] = {}
  for titulo in titulos:
    ancora = titulo.find("a", class_="protocoloNormal")
    protocolo = extrair_protocolo(_texto(ancora) if ancora else _texto(titulo))
    if not protocolo or protocolo in resultados:
      continue

    span = titulo.find("span")
    tipo = _texto(span).rstrip() if span else None
    if tipo:
      # O rótulo termina em "... Nº "; o número vem no <a> seguinte.
      tipo = re.sub(r"\s*N[ºo°]\s*$", "", tipo).strip() or None

    item = ProcessoDescoberto(
      protocolo=protocolo,
      tipo_processo=tipo,
      link_acesso=ancora.get("href") if ancora else None,
    )

    # Percorre as linhas do bloco até o próximo registro.
    for irmao in titulo.find_next_siblings("tr"):
      if _tem_classe(irmao, "pesquisaTituloRegistro"):
        break
      for celula in irmao.find_all("td"):
        if _tem_classe(celula, "pesquisaSnippet"):
          trecho = _texto(celula).strip(". ")
          if trecho:
            item.especificacao = trecho[:2000]
          continue
        if not _tem_classe(celula, "pesquisaMetatag"):
          continue
        rotulo = _texto(celula.find("b")).lower()
        if "unidade" in rotulo:
          sigla = celula.find("a", class_="ancoraSigla")
          item.unidade_geradora_sigla = _texto(sigla) or None
        elif "inclus" in rotulo or "data" in rotulo:
          item.data_autuacao = parse_data(_texto(celula))

    resultados[protocolo] = item

  return list(resultados.values())


def _primeira_sigla(texto: str, ignorar: str | None = None) -> str | None:
  for achado in RE_SIGLA.finditer(texto or ""):
    sigla = achado.group(0)
    if ignorar and sigla in ignorar:
      continue
    if "/" not in sigla and len(sigla) < 3:
      continue
    if RE_PROTOCOLO.match(sigla):
      continue
    return sigla
  return None


def tem_proxima_pagina(html: str, offset_atual: int = 0) -> bool:
  """Há mais páginas depois do offset atual?"""
  if proximo_offset(html or "", offset_atual) is not None:
    return True
  soup = BeautifulSoup(html or "", "html.parser")
  for no in soup.find_all(["a", "img", "input"]):
    rotulo = " ".join(
      str(no.get(atributo, "")) for atributo in ("id", "title", "alt", "value", "onclick")
    ).lower()
    eh_proxima = "proxima" in rotulo or "próxima" in rotulo or "paginaproxima" in rotulo
    if eh_proxima and "disabled" not in str(no.get("class", "")).lower():
      return True
  return False


def sessao_expirada(html: str) -> bool:
  """O SEI devolve 200 com tela de login quando a sessão cai."""
  marcador = (html or "").lower()
  return any(
    pista in marcador
    for pista in (
      "sessao expirada",
      "sessão expirada",
      "acesso negado",
      'name="pwdsenha"',
      "usuario_sistema_logar",
    )
  )
