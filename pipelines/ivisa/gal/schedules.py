# -*- coding: utf-8 -*-
from pipelines.utils.schedules import create_schedule

# Varredura diária às 07h (cadência 24h do ivisa-flows).
# ATENÇÃO: depende do cookie GAL_SESSAO_COOKIE estar válido no Infisical —
# renovação manual pelo operador (captcha). Falha => alerta Discord.
schedules = [
  create_schedule(
    parameters={"environment": "prod", "pagina_tamanho": 100, "limite_paginas": None},
    interval="daily",
    config={"hour": 7, "minute": 0},
  )
]
