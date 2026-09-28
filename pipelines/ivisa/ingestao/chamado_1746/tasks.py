# -*- coding: utf-8 -*-
import hashlib
import hmac
import json
from datetime import date

import httpx
from google.cloud import bigquery
from prefect import task

from pipelines.utils.infisical import get_secret
from pipelines.utils.logger import log
from pipelines.utils.prefect import authenticated_task

from .constants import constants as C


@authenticated_task
def buscar_chamados_datario(
    data_inicio: date,
    data_fim: date,
    environment: str = "dev",
) -> list[dict]:
    """
    Consulta BigQuery datario e retorna chamados das unidades IVISA no período.
    Filtra por data_particao para evitar scan completo da tabela (~6.8 GB).
    """
    unit_ids_sql = ", ".join(str(u) for u in C.IVISA_UNIT_IDS.value)
    query = f"""
        SELECT
            id_chamado,
            categoria,
            tipo,
            subtipo,
            status,
            situacao,
            tipo_situacao,
            dentro_prazo,
            reclamacoes,
            id_unidade_organizacional,
            nome_unidade_organizacional,
            id_bairro,
            longitude,
            latitude,
            CAST(data_inicio AS STRING) AS data_inicio,
            CAST(data_fim AS STRING) AS data_fim,
            CAST(data_particao AS STRING) AS data_particao
        FROM `{C.DATARIO_PROJECT.value}.{C.DATARIO_DATASET.value}.{C.DATARIO_TABLE.value}`
        WHERE data_particao BETWEEN '{data_inicio}' AND '{data_fim}'
          AND CAST(id_unidade_organizacional AS INT64) IN ({unit_ids_sql})
    """
    log(f"[1746] Consultando datario: {data_inicio} → {data_fim}", level="info")
    client = bigquery.Client()
    rows = list(client.query(query).result())
    log(f"[1746] {len(rows)} chamados encontrados", level="info")
    return [dict(r) for r in rows]


@task
def montar_lote(chamados: list[dict]) -> list[dict]:
    """
    Converte linhas do datario no formato contracts/ingestao/1746-lote-v1.json.
    Puro — sem I/O.
    """
    registros = []
    for c in chamados:
        # Serializa valores não-string para string (BigQuery pode devolver Decimal, etc.)
        bruto = {k: str(v) if v is not None else None for k, v in c.items()}
        registros.append(
            {
                "kind": "visto",
                "source_ref": str(c["id_chamado"]),
                "conteudo": {
                    "numero": str(c["id_chamado"]),
                    "bruto": bruto,
                },
            }
        )
    return registros


@task
def postar_lote_corevisa(
    registros: list[dict],
    run_id: str,
    environment: str = "dev",
) -> dict:
    """
    Envia registros ao COREVISA em fatias de LOTE_MAX via
    POST /v1/ingestao/1746/lote com HMAC-SHA256 no header X-Ingestao-Signature.
    """
    corevisa_url = get_secret(
        path=C.INFISICAL_PATH.value,
        secret_name=C.INFISICAL_COREVISA_URL.value,
        environment=environment,
    )
    lote_secret = get_secret(
        path=C.INFISICAL_PATH.value,
        secret_name=C.INFISICAL_COREVISA_LOTE_SECRET.value,
        environment=environment,
    )

    endpoint = f"{corevisa_url.rstrip('/')}/v1/ingestao/1746/lote"
    tamanho = C.LOTE_MAX.value
    resultados = []

    for i in range(0, max(len(registros), 1), tamanho):
        fatia = registros[i : i + tamanho]
        if not fatia:
            break

        corpo = json.dumps(
            {"run": {"robo": "ivisa-1746-datario", "run_id": run_id}, "registros": fatia},
            ensure_ascii=False,
        ).encode("utf-8")

        assinatura = hmac.new(
            lote_secret.encode("utf-8"), corpo, hashlib.sha256
        ).hexdigest()

        log(f"[1746] Postando lote {i // tamanho + 1} ({len(fatia)} registros)", level="info")
        resp = httpx.post(
            endpoint,
            content=corpo,
            headers={
                "Content-Type": "application/json",
                "X-Ingestao-Signature": assinatura,
            },
            timeout=60,
        )
        resp.raise_for_status()
        resultados.append(
            {"lote": i // tamanho, "status": resp.status_code, "corpo": resp.json()}
        )

    log(f"[1746] {len(registros)} registros postados em {len(resultados)} lote(s)", level="info")
    return {"total_enviados": len(registros), "lotes": resultados}
