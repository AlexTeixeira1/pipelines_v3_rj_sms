"""Contratos de dados da descoberta do SEI. Portado de `adm-predial`
(`app/services/sei/tipos.py`) — só o que a descoberta usa."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class ProcessoDescoberto:
  """Resultado de uma linha da pesquisa do SEI."""

  protocolo: str
  tipo_processo: str | None = None
  data_autuacao: datetime | None = None
  unidade_geradora_sigla: str | None = None
  especificacao: str | None = None
  link_acesso: str | None = None
