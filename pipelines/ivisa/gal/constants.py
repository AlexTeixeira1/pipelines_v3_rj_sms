# -*- coding: utf-8 -*-
"""Constantes do flow GAL (instância RJ, módulo Ambiental).

ATENÇÃO: o login do GAL tem CAPTCHA humano por acesso — não é automatizável
(ver decision seção 14.4). O cookie de sessão (PHPSESSID) é resolvido pelo
operador localmente e gravado no Infisical /ivisa como GAL_SESSAO_COOKIE (JSON).
Este flow só REUSA o cookie; quando expira, falha com aviso claro e o operador
renova o secret.
"""

from enum import Enum


class constants(Enum):
  FONTE = "gal"

  # Secret no Infisical /ivisa — JSON com os cookies de sessão, gravado pelo
  # operador após resolver o captcha localmente.
  SECRET_COOKIE = "GAL_SESSAO_COOKIE"

  BASE_URL = "https://gal.riodejaneiro.sus.gov.br"
  HTTP_TIMEOUT = 60.0
  SYNC_DELAY_MS = 1500  # intervalo de cortesia — não reduzir
  TLS_VERIFY = False  # certificado da instância está expirado (docs/fontes/gal.md)

  # Recorte IVISA
  MUNICIPIOS = ["Rio de Janeiro"]

  PAGINA_TAMANHO = 100
