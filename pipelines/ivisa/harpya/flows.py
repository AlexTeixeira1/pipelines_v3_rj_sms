# -*- coding: utf-8 -*-
from pipelines.constants import CIT
from pipelines.utils.prefect import flow, flow_config

from .schedules import schedules
from .tasks import varrer_periodo


@flow(
  name="Extracao: ivisa harpya corevisa",
  owners=[CIT.PEDRO_ID.value],
  tags=["IVISA", "HARPYA", "COREVISA"],
)
def ivisa_harpya_corevisa(environment: str = "dev", dias_janela: int = 1) -> dict:
  """Varre a tela de gestão do Harpya por período, busca o laudo completo de
  cada amostra e posta o HTML cru em POST /v1/ingestao/harpya/lote.

  O COREVISA parseia o laudo. Secrets HARPYA_USERNAME/PASSWORD no Infisical
  /ivisa-rio. Login sem captcha — sessão renovada a cada run.
  """
  return varrer_periodo(dias_janela=dias_janela, environment=environment)


_flows = [flow_config(flow=ivisa_harpya_corevisa, schedules=schedules)]
