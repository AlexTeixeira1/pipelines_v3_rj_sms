# -*- coding: utf-8 -*-
from pipelines.utils.schedules import create_schedule

# Sem "modificado desde" na API — varredura completa diária às 05h.
schedules = [
    create_schedule(
        parameters={"environment": "prod"},
        interval="daily",
        config={"hour": 5, "minute": 0},
    )
]
