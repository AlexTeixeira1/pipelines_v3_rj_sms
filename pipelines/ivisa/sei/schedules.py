# -*- coding: utf-8 -*-
from pipelines.utils.schedules import create_schedule

# Descoberta de 12 em 12 horas (cadência 2h do ivisa-flows não é expressável
# com o helper do repo; 12-hours é o mais frequente disponível abaixo de daily).
schedules = [
  create_schedule(
    parameters={"environment": "prod", "janela_dias": 3, "max_paginas": 50},
    interval="12-hours",
    config={"hour": 2, "minute": 0},
  )
]
