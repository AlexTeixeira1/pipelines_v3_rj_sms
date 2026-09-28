# -*- coding: utf-8 -*-
"""Constantes do flow e-SISBI."""

from enum import Enum


class constants(Enum):
    FONTE = "esisbi"
    RECURSO_ESTAB = "estabelecimentos-sisbi"
    API_BASE_URL = "https://sistemasweb.agricultura.gov.br/sisbi_api"
    HTTP_TIMEOUT = 60.0
    PAGE_SIZE = 100  # count <= 200; acima fica instável
    SYNC_DELAY_MS = 200

    # Recorte IVISA — UF no servidor (sgUf), município client-side
    UF = "RJ"
    MUNICIPIOS = ["Rio de Janeiro"]

    # UA não-browser devolve o shell da SPA ("SGSI") em vez de JSON
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://sistemasweb.agricultura.gov.br/sgsi/",
    }
