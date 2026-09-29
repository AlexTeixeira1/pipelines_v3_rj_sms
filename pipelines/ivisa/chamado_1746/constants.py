# -*- coding: utf-8 -*-
from enum import Enum


class constants(Enum):
  # Secrets COREVISA_URL/LOTE ficam no _shared (path /ivisa-rio no Infisical)
  FONTE = "1746"

  # ID raiz do IVISA-RIO no datario (confirmado ao vivo 2026-09-23 via bq show)
  IVISA_ROOT_UNIT_ID = "610"

  # Snapshot das 49 unidades subordinadas ao root 610 (BFS confirmado 2026-09-23).
  # Usado como fallback se a resolução ao vivo falhar.
  IVISA_UNIT_IDS = [
    610,
    612,
    613,
    614,
    615,
    616,
    618,
    624,
    625,
    626,
    627,
    628,
    629,
    630,
    631,
    632,
    633,
    634,
    635,
    636,
    640,
    641,
    644,
    646,
    647,
    648,
    773,
    1252,
    1253,
    1254,
    1255,
    1256,
    1257,
    1273,
    1287,
    1288,
    1289,
    1293,
    1308,
    1309,
    1391,
    1474,
    1475,
    1485,
    1490,
    1491,
    1620,
    1736,
    1786,
  ]

  DATARIO_PROJECT = "datario"
  DATARIO_DATASET = "adm_central_atendimento_1746"
  DATARIO_TABLE = "chamado"
