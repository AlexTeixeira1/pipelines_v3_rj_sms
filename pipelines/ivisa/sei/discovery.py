"""Fontes de descoberta de processos novos.

Portado de `adm-predial` (`app/services/sei/discovery.py`) — fase 1, nunca
chegou a ser portada pro corevisa (`docs/fontes/sei.md` lá: só a fase 2,
gateway, existe). O `FonteDescoberta` existe para isolar o único ponto frágil
da integração. Se a SUBG um dia expuser um endpoint de listagem, basta uma
nova implementação aqui — o flow e o envio pro corevisa não mudam.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import date
from typing import Protocol

from . import parser
from .client_web import SeiSessaoWeb
from .tipos import ProcessoDescoberto

_log = logging.getLogger(__name__)


class FonteDescoberta(Protocol):
  async def listar_protocolos(
    self, inicio: date, fim: date
  ) -> AsyncIterator[ProcessoDescoberto]: ...  # pragma: no cover - contrato


class DiscoveryWeb:
  """Descoberta pela pesquisa autenticada do SEI, paginando por período."""

  def __init__(
    self,
    sessao: SeiSessaoWeb,
    orgaos: list[str] | None = None,
    max_paginas: int = 50,
    id_unidade: str | None = None,
    considerar_tramitacao: bool = False,
    tipo_data: str = "G",
    restringir_orgao: bool = True,
  ) -> None:
    self._sessao = sessao
    self._orgaos = orgaos or []
    self._max_paginas = max_paginas
    self._id_unidade = id_unidade
    self._considerar_tramitacao = considerar_tramitacao
    self._tipo_data = tipo_data
    self._restringir_orgao = restringir_orgao
    self.paginas_lidas = 0
    self.total_informado: int | None = None
    self.parou_por_limite = False

  async def listar_protocolos(
    self, inicio: date, fim: date
  ) -> AsyncIterator[ProcessoDescoberto]:
    vistos: set[str] = set()
    offset = 0
    pagina = 0

    while True:
      html = await self._sessao.pesquisar_periodo(
        inicio,
        fim,
        self._orgaos or None,
        offset=offset,
        id_unidade=self._id_unidade,
        considerar_tramitacao=self._considerar_tramitacao,
        tipo_data=self._tipo_data,
        restringir_orgao=self._restringir_orgao,
      )
      pagina += 1
      self.paginas_lidas = pagina
      if self.total_informado is None:
        self.total_informado = parser.total_resultados(html)

      resultados = parser.parse_resultados_pesquisa(html)

      if not resultados and pagina == 1:
        _log.warning(
          "Pesquisa SEI de %s a %s não retornou nenhum protocolo reconhecível. "
          "Ou o período está vazio, ou a marcação do SEI mudou — capture o HTML "
          "em tests/fixtures/sei/ e ajuste o parser.",
          inicio,
          fim,
        )

      novos = 0
      for item in resultados:
        if item.protocolo in vistos:
          continue
        vistos.add(item.protocolo)
        novos += 1
        yield item

      if pagina >= self._max_paginas:
        self.parou_por_limite = True
        _log.warning(
          "Limite de %d páginas atingido na janela %s..%s", self._max_paginas, inicio, fim
        )
        break
      if novos == 0:
        break

      proximo = parser.proximo_offset(html, offset)
      if proximo is None:
        break
      offset = proximo


class DiscoveryManual:
  """Lista fixa de protocolos.

  Serve para reprocessar um lote conhecido e para testar o fluxo inteiro sem
  tocar na rede.
  """

  def __init__(self, protocolos: list[str] | list[ProcessoDescoberto]) -> None:
    self._itens = [
      p
      if isinstance(p, ProcessoDescoberto)
      else ProcessoDescoberto(protocolo=str(p).strip().upper())
      for p in protocolos
    ]

  async def listar_protocolos(
    self, inicio: date, fim: date
  ) -> AsyncIterator[ProcessoDescoberto]:
    for item in self._itens:
      yield item
