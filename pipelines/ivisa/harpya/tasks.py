# -*- coding: utf-8 -*-
"""Tasks do Harpya — varredura da tela de gestão por período + busca do laudo
completo de cada amostra. Login usuário/senha (sem captcha), uma sessão por run.

Cru vai para POST /v1/ingestao/harpya/lote: `kind="laudo"` (HTML cru + pdf_url)
ou `kind="sem_laudo"`. Este flow não parseia nada — só busca.
"""

import asyncio
import uuid
from datetime import UTC, date, datetime, timedelta

from prefect import task

from pipelines.ivisa._shared.corevisa import ItemLote, RunMeta, enviar_lote
from pipelines.utils.infisical import get_secret
from pipelines.utils.logger import log

from .client import HarpyaNaoEncontrado, HarpyaSessao
from .constants import constants as C
from .parser import normalizar_codigo_harpya

INFISICAL_PATH = "/ivisa-rio"


async def _varrer(dias_janela: int, environment: str) -> dict:
  username = get_secret(
    path=INFISICAL_PATH, secret_name=C.SECRET_USERNAME.value, environment=environment
  )
  password = get_secret(
    path=INFISICAL_PATH, secret_name=C.SECRET_PASSWORD.value, environment=environment
  )

  run_id = f"harpya-{uuid.uuid4().hex[:12]}"
  buscou_em = datetime.now(UTC)
  fim = date.today()
  inicio = fim - timedelta(days=dias_janela)

  itens: list[ItemLote] = []
  async with HarpyaSessao(username=username, password=password) as sessao:
    await sessao.login()
    linhas = await sessao.buscar_amostras_por_periodo(
      inicio.strftime("%d/%m/%Y"), fim.strftime("%d/%m/%Y")
    )
    log(f"harpya: {len(linhas)} amostra(s) na janela {inicio}..{fim}", level="info")

    vistos: set[str] = set()
    for linha in linhas:
      numero = linha.get("numero_amostra")
      if not numero:
        continue
      codigo = normalizar_codigo_harpya(numero)
      if codigo in vistos:
        continue
      vistos.add(codigo)

      try:
        resultado = await sessao.buscar_laudo_html(codigo)
      except HarpyaNaoEncontrado:
        itens.append(
          ItemLote(
            kind="sem_laudo", source_ref=codigo, conteudo={"codigo_harpya": codigo}
          )
        )
        continue
      laudo_html, pdf_url = resultado
      itens.append(
        ItemLote(
          kind="laudo",
          source_ref=codigo,
          conteudo={
            "codigo_harpya": codigo,
            "pdf_url": pdf_url,
            "laudo_html": laudo_html,
          },
        )
      )

  run = RunMeta(
    robo="harpya-flow",
    run_id=run_id,
    buscou_em=buscou_em,
    terminou_em=datetime.now(UTC),
    janela_inicio=datetime.combine(inicio, datetime.min.time(), tzinfo=UTC),
    janela_fim=datetime.combine(fim, datetime.min.time(), tzinfo=UTC),
  )
  resultado = enviar_lote(C.FONTE.value, run, itens, environment=environment)
  log(f"harpya: {len(itens)} item(ns) enviado(s) ao COREVISA — {resultado}", level="info")
  return resultado


@task(name="harpya-varrer-periodo")
def varrer_periodo(dias_janela: int, environment: str) -> dict:
  return asyncio.run(_varrer(dias_janela, environment))
