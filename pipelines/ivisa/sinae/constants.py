# -*- coding: utf-8 -*-
"""Constantes do flow SINAE (WS Fazenda Estabelecimento, SOAP)."""

from enum import Enum


class constants(Enum):
  FONTE = "sinae"
  SECRET_TOKEN = "SINAE_TOKEN"  # no Infisical /ivisa-rio
  WSDL_URL = (
    "https://wsp01.smf.rio.rj.gov.br/DotNet/Ws/WSFazenda_Estabelecimento/"
    "WSFazenda_Estabelecimento.svc?wsdl"
  )
