# -*- coding: utf-8 -*-
from pipelines.constants import CIT
from pipelines.utils.prefect import flow, flow_config

from .schedules import schedules
from .tasks import descobrir_e_enriquecer


@flow(
  name="Extracao: ivisa sei corevisa",
  owners=[CIT.PEDRO_ID.value],
  tags=["IVISA", "SEI", "COREVISA"],
)
def ivisa_sei_corevisa(
  environment: str = "dev", janela_dias: int = 3, max_paginas: int = 50
) -> dict:
  """Descobre protocolos SEI novos pela pesquisa autenticada (web, sem
  captcha), enriquece cada um via gateway e posta kind=verificado em
  POST /v1/ingestao/sei/lote.

  O COREVISA decide tem_ivisa e o ciclo de vida do processo. Secrets
  SEI_USUARIO/SENHA/ORGAO + SEI_API_* no Infisical /ivisa-rio.

  ATENÇÃO: o login web headless precisa ser validado no ambiente Cloud Run
  (confirmar que não há captcha/2FA lá) antes de agendar em prod.
  """
  return descobrir_e_enriquecer(
    janela_dias=janela_dias, max_paginas=max_paginas, environment=environment
  )


_flows = [flow_config(flow=ivisa_sei_corevisa, schedules=schedules)]
