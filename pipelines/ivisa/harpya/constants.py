# -*- coding: utf-8 -*-
"""Constantes do flow Harpya (DATASUS/CGLAB)."""

from enum import Enum


class constants(Enum):
  FONTE = "harpya"
  SECRET_USERNAME = "HARPYA_USERNAME"  # no Infisical /ivisa
  SECRET_PASSWORD = "HARPYA_PASSWORD"

  BASE_URL = "https://harpya.datasus.gov.br/harpya"
  DIAS_JANELA = 1
