# -*- coding: utf-8 -*-
from datetime import date, timedelta
from uuid import uuid4

from pipelines.constants import CIT
from pipelines.ivisa.ingestao.chamado_1746.schedules import schedules
from pipelines.ivisa.ingestao.chamado_1746.tasks import (
    buscar_chamados_datario,
    montar_lote,
    postar_lote_corevisa,
)
from pipelines.utils.prefect import flow, flow_config


@flow(
    name="Extração: 1746 → COREVISA",
    owners=[CIT.PEDRO_ID.value],
    tags=["IVISA", "1746", "COREVISA"],
)
def ivisa_1746_corevisa(
    environment: str = "dev",
    janela_dias: int = 7,
):
    """
    Descobre chamados 1746 das unidades IVISA via datario (BigQuery público)
    e posta os registros crus no COREVISA via POST /v1/ingestao/1746/lote.

    O COREVISA normaliza, grava no event_store e emite eventos 1746.chamado.visto.
    Idempotente: reprocessar a mesma janela não duplica eventos (ON CONFLICT DO NOTHING).

    Próximos flows a criar (não neste escopo):
    - enriquecimento VoxSUS (kind=chamado) por número já visto
    - classificação 1746__desinterdicao / 1746__denuncia (Parte 2A)
    """
    run_id = str(uuid4())
    data_fim = date.today()
    data_inicio = data_fim - timedelta(days=janela_dias)

    chamados = buscar_chamados_datario(
        data_inicio=data_inicio,
        data_fim=data_fim,
        environment=environment,
    )
    registros = montar_lote(chamados=chamados)
    resultado = postar_lote_corevisa(
        registros=registros,
        run_id=run_id,
        environment=environment,
    )
    return resultado


_flows = [
    flow_config(
        flow=ivisa_1746_corevisa,
        schedules=schedules,
    )
]
