# -*- coding: utf-8 -*-
from pipelines.utils.schedules import create_schedule

# Sem varredura — só checa a fila /solicitacoes. Roda de hora em hora
# (sem custo se a fila estiver vazia; não há período a cobrir).
schedules = [
  create_schedule(
    parameters={"environment": "prod"}, interval="hourly", config={"minute": 0}
  )
]
