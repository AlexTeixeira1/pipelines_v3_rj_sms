# -*- coding: utf-8 -*-
"""Constantes do flow SEI.

Secrets (usuário/senha web, token do gateway) vêm do Infisical /ivisa. Valores
públicos de comportamento (URLs, janelas, delays) ficam aqui.
"""

from enum import Enum


class constants(Enum):
  FONTE = "sei"

  # Secrets no Infisical /ivisa
  SECRET_USUARIO = "SEI_USUARIO"
  SECRET_SENHA = "SEI_SENHA"
  SECRET_ORGAO = "SEI_ORGAO"
  SECRET_API_SYSTEM_TOKEN = "SEI_API_SYSTEM_TOKEN"
  SECRET_API_REQUESTER = "SEI_API_REQUESTER"
  SECRET_API_ID_UNIDADE = "SEI_API_ID_UNIDADE"

  # Configuração pública (não-secreta)
  BASE_URL = "https://prefeitura.sei.rio"
  API_BASE_URL = "https://sei.gateway.subgsms.rio"
  HTTP_TIMEOUT = 30.0
  SYNC_DELAY_MS = 1000
  SYNC_JANELA_DIAS = 3
  SYNC_ORGAOS = ""  # CSV; vazio = sem filtro de órgão
  RESTRINGIR_ORGAO = True
  MAX_PAGINAS = 50
