# -*- coding: utf-8 -*-
from pipelines.constants import CIT
from pipelines.utils.prefect import flow, flow_config

from .tasks import contar_letras, saudar


@flow(
  name="IVISA: Hello World",
  description="Flow mínimo para validar setup do Prefect no contexto IVISA. Sem I/O externo.",
  owners=[CIT.PEDRO_ID.value],
  tags=["IVISA", "teste"],
)
def ivisa_hello_world(nome: str = "IVISA", environment: str = "dev") -> dict:
  mensagem = saudar(nome=nome)
  total = contar_letras(texto=mensagem)
  return {"mensagem": mensagem, "caracteres": total}


_flows = [flow_config(flow=ivisa_hello_world, schedules=[])]
