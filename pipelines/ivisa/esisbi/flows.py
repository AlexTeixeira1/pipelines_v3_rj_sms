# -*- coding: utf-8 -*-
from pipelines.constants import CIT
from pipelines.utils.prefect import flow, flow_config

from .schedules import schedules
from .tasks import varrer_recorte


@flow(
  name="Extracao: ivisa esisbi corevisa",
  owners=[CIT.PEDRO_ID.value],
  tags=["IVISA", "ESISBI", "COREVISA"],
)
def ivisa_esisbi_corevisa(environment: str = "dev") -> dict:
  """Varre o recorte IVISA no e-SISBI (API pública) e posta um item por
  estabelecimento em POST /v1/ingestao/esisbi/lote, mais um sweep_completo
  ao fim se a varredura terminou sem erro.

  Sem credencial: fonte pública, só precisa dos secrets COREVISA_URL/LOTE.
  """
  return varrer_recorte(environment=environment)


_flows = [flow_config(flow=ivisa_esisbi_corevisa, schedules=schedules)]
