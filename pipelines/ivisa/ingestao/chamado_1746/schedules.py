# -*- coding: utf-8 -*-
from datetime import datetime, timedelta

from prefect.schedules import Interval

from pipelines.constants import constants as global_constants

# Roda diariamente às 04h (horário de Brasília), janela de 7 dias.
# Janela larga compensa dias em que o flow falhou — o ON CONFLICT DO NOTHING
# do COREVISA garante idempotência em reprocessamentos.
_anchor = datetime(2026, 1, 1, 4, 0, tzinfo=global_constants.TIMEZONE.value)

schedules = [
    Interval(
        timedelta(days=1),
        anchor_date=_anchor,
        timezone=global_constants.TIMEZONE_NAME.value,
        parameters={"environment": "prod", "janela_dias": 7},
    )
]
