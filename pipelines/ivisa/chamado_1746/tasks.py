# -*- coding: utf-8 -*-
"""Tasks do 1746 — descoberta em lote via datario (BigQuery).

Este flow cobre só a descoberta (`kind="visto"`). O enriquecimento VoxSUS
(`kind="chamado"`/`sem_chamado`) e a classificação de eventos de ação
(`1746__desinterdicao`/`1746__denuncia`) são flows futuros.
"""

import uuid
from datetime import UTC, date, datetime

from google.cloud import bigquery
from prefect import task

from pipelines.ivisa._shared.corevisa import ItemLote, RunMeta, enviar_lote
from pipelines.utils.logger import log
from pipelines.utils.prefect import authenticated_task

from .constants import constants as C


@authenticated_task(name="1746-buscar-datario", retries=5, retry_delay_seconds=30)
def buscar_chamados_datario(data_inicio: date, data_fim: date) -> list[dict]:
  """Consulta BigQuery datario e retorna chamados das unidades IVISA no
  período. Filtra por data_particao para evitar scan completo da tabela."""
  unit_ids_sql = ", ".join(str(u) for u in C.IVISA_UNIT_IDS.value)
  query = f"""
        SELECT
            id_chamado, categoria, tipo, subtipo, status, situacao,
            tipo_situacao, dentro_prazo, reclamacoes,
            id_unidade_organizacional, nome_unidade_organizacional,
            id_bairro, longitude, latitude,
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


@task(name="1746-montar-e-enviar")
def montar_e_enviar(chamados: list[dict], environment: str) -> dict:
  """Converte linhas do datario em itens `kind=visto` e posta no COREVISA."""
  run_id = f"1746-{uuid.uuid4().hex[:12]}"
  buscou_em = datetime.now(UTC)

  itens: list[ItemLote] = []
  vistos: set[str] = set()
  for c in chamados:
    numero = str(c.get("id_chamado") or "").strip()
    if not numero or numero in vistos:
      continue
    vistos.add(numero)
    bruto = {k: str(v) if v is not None else None for k, v in c.items()}
    itens.append(
      ItemLote(
        kind="visto", source_ref=numero, conteudo={"numero": numero, "bruto": bruto}
      )
    )

  run = RunMeta(
    robo="1746-datario", run_id=run_id, buscou_em=buscou_em, terminou_em=datetime.now(UTC)
  )
  resultado = enviar_lote(C.FONTE.value, run, itens, environment=environment)
  log(
    f"[1746] {len(itens)} chamado(s) enviado(s) ao COREVISA — {resultado}", level="info"
  )
  return resultado
