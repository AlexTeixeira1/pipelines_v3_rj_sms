# -*- coding: utf-8 -*-
from pipelines.utils.schedules import create_schedule

# MAPA publica o dataset inteiro 1x/semana — varredura semanal aos sábados 03h.
schedules = [
  create_schedule(
    parameters={"environment": "prod"},
    interval="weekly",
    config={"weekday": "saturday", "hour": 3, "minute": 0},
  )
]
