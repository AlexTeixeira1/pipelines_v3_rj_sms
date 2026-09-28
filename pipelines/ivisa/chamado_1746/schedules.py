# -*- coding: utf-8 -*-
from pipelines.utils.schedules import create_schedule

# Diário às 04h; janela de 7 dias compensa dias em que o flow falhou
# (o ON CONFLICT DO NOTHING do COREVISA garante idempotência no reprocessamento).
schedules = [
    create_schedule(
        parameters={"environment": "prod", "janela_dias": 7},
        interval="daily",
        config={"hour": 4, "minute": 0},
    )
]
