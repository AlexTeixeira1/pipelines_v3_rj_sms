# -*- coding: utf-8 -*-
from prefect import task

from pipelines.utils.logger import log


@task
def saudar(nome: str) -> str:
  mensagem = f"Olá, {nome}! Flow IVISA rodando."
  log(mensagem, level="info")
  return mensagem


@task
def contar_letras(texto: str) -> int:
  total = len(texto)
  log(f"Texto tem {total} caracteres.", level="info")
  return total
