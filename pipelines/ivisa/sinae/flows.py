# -*- coding: utf-8 -*-
from pipelines.constants import CIT
from pipelines.utils.prefect import flow, flow_config

from .schedules import schedules
from .tasks import drenar_solicitacoes


@flow(
  name="Extracao: ivisa sinae corevisa",
  owners=[CIT.PEDRO_ID.value],
  tags=["IVISA", "SINAE", "COREVISA"],
)
def ivisa_sinae_corevisa(environment: str = "dev") -> dict:
  """Drena POST /v1/ingestao/sinae/solicitar: busca cadastro por CNPJ no WS
  Fazenda Estabelecimento (SOAP) e posta em POST /v1/ingestao/sinae/lote.

  Sem varredura — só responde ao que foi pedido. Secret SINAE_TOKEN no
  Infisical /ivisa-rio.
  """
  return drenar_solicitacoes(environment=environment)


_flows = [flow_config(flow=ivisa_sinae_corevisa, schedules=schedules)]
