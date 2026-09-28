# -*- coding: utf-8 -*-
from pipelines.constants import CIT
from pipelines.utils.prefect import flow, flow_config

from .schedules import schedules
from .tasks import montar_e_enviar


@flow(
  name="Extracao: ivisa sipeagro corevisa",
  owners=[CIT.PEDRO_ID.value],
  tags=["IVISA", "SIPEAGRO", "COREVISA"],
)
def ivisa_sipeagro_corevisa(environment: str = "dev") -> dict:
  """Baixa os 9 CSVs do SIPEAGRO (MAPA, público), recorta pro recorte IVISA
  (UF/município) e posta um item por área em POST /v1/ingestao/sipeagro/lote.

  O COREVISA parseia e detecta quem sumiu dentro do recorte. Sem credencial:
  fonte pública, só precisa dos secrets COREVISA_URL/LOTE no Infisical /ivisa.
  """
  return montar_e_enviar(environment=environment)


_flows = [flow_config(flow=ivisa_sipeagro_corevisa, schedules=schedules)]
