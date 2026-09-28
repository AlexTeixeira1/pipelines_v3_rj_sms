# -*- coding: utf-8 -*-
from datetime import date, timedelta

from pipelines.constants import CIT
from pipelines.utils.prefect import flow, flow_config

from .schedules import schedules
from .tasks import buscar_chamados_datario, montar_e_enviar


@flow(
    name="Extracao: ivisa 1746 corevisa",
    owners=[CIT.PEDRO_ID.value],
    tags=["IVISA", "1746", "COREVISA"],
)
def ivisa_1746_corevisa(environment: str = "dev", janela_dias: int = 7) -> dict:
    """Descobre chamados 1746 das unidades IVISA via datario (BigQuery público)
    e posta os registros crus em POST /v1/ingestao/1746/lote (kind=visto).

    O COREVISA normaliza e emite eventos 1746.chamado.visto. Idempotente:
    reprocessar a mesma janela não duplica (ON CONFLICT DO NOTHING).

    Próximos flows (fora deste escopo): enriquecimento VoxSUS (kind=chamado),
    classificação 1746__desinterdicao/1746__denuncia (Parte 2A).
    """
    data_fim = date.today()
    data_inicio = data_fim - timedelta(days=janela_dias)

    chamados = buscar_chamados_datario(data_inicio=data_inicio, data_fim=data_fim)
    return montar_e_enviar(chamados=chamados, environment=environment)


_flows = [flow_config(flow=ivisa_1746_corevisa, schedules=schedules)]
