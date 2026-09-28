# -*- coding: utf-8 -*-
from pipelines.utils.schedules import create_schedule

# Varredura diária às 06h (cadência 24h do ivisa-flows).
schedules = [
  create_schedule(
    parameters={"environment": "prod", "dias_janela": 1},
    interval="daily",
    config={"hour": 6, "minute": 0},
  )
]
