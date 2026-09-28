"""HTML/AJAX-XML do Harpya -> primitivas de scraping. Portado de
`sisfoco-api/app/services/harpya_service.py` — só o que a **descoberta**
(varredura da tela de gestão, achar `numero_amostra`) usa. O parsing do
laudo individual (ficha/ensaios/conclusão) fica no corevisa
(`infra/normalizacao/harpya/parser.py`) — o cru (`laudo_html`) viaja intacto.

Sem rede, sem estado.
"""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

# Mapeamento campo -> índice na tabela de gestão (baseado no HTML capturado
# pelo SISFOCO contra a instância real do Harpya).
_COL = {
  "numero_amostra": 1,
  "bairro_responsavel": 4,
  "categoria_produto": 5,
  "data_coleta": 12,
  "data_cadastro": 13,
  "descricao_produto": 21,
  "numero_laudo": 38,
  "nome_comercial": 43,
  "laboratorio": 31,
  "municipio_coleta": 34,
  "programa_laboratorial": 49,
  "requerente": 51,
  "situacao_amostra": 54,
  "complemento_conclusao": 81,
  "conclusao": 82,
  "data_fechamento": 84,
}


def normalizar_codigo_harpya(codigo: str) -> str:
  """'4314.1p.0/2026' -> '04314.1P.0/2026' (ordinal com 5 dígitos, tipo maiúsculo)."""
  codigo = (codigo or "").strip()
  m = re.match(r"^0*(\d+)\.([^.]+)\.(\d+)/(\d{4})$", codigo)
  if m:
    return f"{m.group(1).zfill(5)}.{m.group(2).upper()}.{m.group(3)}/{m.group(4)}"
  return codigo


def decompor_codigo_harpya(codigo: str) -> dict[str, str]:
  """'{ordinal}.{tipo}.{sequencial}/{ano}' -> campos do formulário de busca.
  Harpya não aceita zeros à esquerda em `busca-numeracao`."""
  m = re.match(r"^0*(\d+)\.([^.]+)\.(\d+)/(\d{4})$", codigo.strip())
  if m:
    return {
      "numeracao": str(int(m.group(1))),
      "tipo": m.group(2),
      "sequencial": m.group(3),
      "ano": m.group(4),
    }
  partes = codigo.split(".")
  return {"numeracao": partes[0], "tipo": "", "sequencial": "0", "ano": ""}


def extrair_viewstate(html: str) -> str:
  soup = BeautifulSoup(html, "html.parser")
  campo = soup.find("input", {"name": "javax.faces.ViewState"})
  if not campo or not campo.get("value"):
    raise RuntimeError("javax.faces.ViewState não encontrado na página.")
  return str(campo["value"])


def extrair_viewstate_ajax(xml_response: str) -> str:
  """ViewState atualizado, da resposta AJAX parcial do JSF."""
  soup = BeautifulSoup(xml_response, "xml")
  vs_tag = soup.find("update", {"id": lambda x: x is not None and "ViewState" in x})
  if vs_tag and vs_tag.text:
    return vs_tag.text.strip()
  raise RuntimeError("ViewState não encontrado na resposta AJAX.")


def extrair_html_ajax(xml_response: str, update_id: str) -> str:
  """Fragmento HTML de uma resposta AJAX parcial do JSF (`<update id=...>`)."""
  soup = BeautifulSoup(xml_response, "xml")
  update_tag = soup.find("update", {"id": update_id})
  if update_tag:
    return update_tag.text

  error_tag = soup.find("error")
  if error_tag:
    msg = error_tag.find("error-message")
    raise RuntimeError(f"Erro JSF: {msg.text if msg else 'desconhecido'}")

  raise RuntimeError(f"Resposta AJAX não continha <update id='{update_id}'>.")


def extrair_row_count(html: str) -> int | None:
  """Total de registros do script PrimeFaces DataTable (`rowCount:N`)."""
  m = re.search(r"rowCount:(\d+)", html)
  return int(m.group(1)) if m else None


def parse_gestao(html: str) -> list[dict[str, Any]]:
  """Linhas da tabela de resultados da tela de gestão (busca inicial)."""
  soup = BeautifulSoup(html, "html.parser")
  tables = soup.find_all("table")
  if len(tables) < 2:
    return []
  tabela = tables[1]
  rows = tabela.find_all("tr")[1:]  # pula header
  return _linhas_de(rows)


def parse_gestao_rows(html: str) -> list[dict[str, Any]]:
  """Variante pra respostas de paginação do PrimeFaces — retornam só <tr>,
  sem <table> em volta."""
  soup = BeautifulSoup(html, "html.parser")
  return _linhas_de(soup.find_all("tr"))


def _linhas_de(rows: Any) -> list[dict[str, Any]]:
  resultado = []
  for row in rows:
    cells = [td.get_text(strip=True) for td in row.find_all("td")]
    if not cells:
      continue
    item = {
      campo: cells[idx] if idx < len(cells) else None for campo, idx in _COL.items()
    }
    resultado.append({k: v or None for k, v in item.items()})
  return resultado
