# -*- coding: utf-8 -*-
from pipelines.constants import CIT
from pipelines.utils.prefect import flow, flow_config

from .schedules import schedules
from .tasks import varrer_laudos


@flow(
  name="Extracao: ivisa gal corevisa",
  owners=[CIT.PEDRO_ID.value],
  tags=["IVISA", "GAL", "COREVISA"],
)
def ivisa_gal_corevisa(
  environment: str = "dev", pagina_tamanho: int = 100, limite_paginas: int | None = None
) -> dict:
  """Varre o grid de laudos finais do GAL (módulo Ambiental), baixa o PDF de
  cada laudo do recorte e posta kind=laudo em POST /v1/ingestao/gal/lote.

  ATENÇÃO (decision §14.4): o login do GAL tem CAPTCHA humano — não
  automatizável. O cookie de sessão vem do Infisical (GAL_SESSAO_COOKIE),
  renovado manualmente pelo operador. Quando expira, o flow falha e dispara
  alerta Discord; alguém precisa renovar o secret.
  """
  return varrer_laudos(
    pagina_tamanho=pagina_tamanho, limite_paginas=limite_paginas, environment=environment
  )


_flows = [flow_config(flow=ivisa_gal_corevisa, schedules=schedules)]
