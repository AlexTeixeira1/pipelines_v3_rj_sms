# -*- coding: utf-8 -*-
"""Tasks do SIPEAGRO — download dos CSVs do MAPA + recorte por UF/município.

O flow não parseia estrutura de negócio: baixa, recorta pro recorte IVISA e
posta o CSV cru como blob. O `parser.py`/`mapper.py` do COREVISA fazem toda a
interpretação (inclusive detectar quem sumiu dentro do recorte).
"""

import csv
import io
import unicodedata
import uuid
from datetime import UTC, datetime

import httpx
from prefect import task

from pipelines.ivisa._shared.corevisa import ItemLote, RunMeta, enviar_lote
from pipelines.utils.logger import log

from .constants import AreaDownload, constants as C


class CsvIndisponivel(RuntimeError):
    pass


def _normalizar(texto: str) -> str:
    sem_acento = (
        unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    )
    return sem_acento.strip().upper()


def _filtrar_por_recorte(csv_bytes: bytes, ufs: set[str], municipios: set[str]) -> bytes:
    """Recorta o CSV por UF/município. Header sem `UF`/`MUNICIPIO` (layout
    mudou) devolve sem filtrar — deixa o parser do COREVISA falhar alto em vez
    de descartar tudo em silêncio."""
    texto = csv_bytes.decode("utf-8", errors="replace")
    linhas = list(csv.reader(io.StringIO(texto), delimiter=";"))
    if not linhas:
        return csv_bytes

    header = linhas[0]
    if "UF" not in header or "MUNICIPIO" not in header:
        return csv_bytes
    idx_uf = header.index("UF")
    idx_mun = header.index("MUNICIPIO")
    municipios_norm = {_normalizar(m) for m in municipios}

    saida = [header]
    for linha in linhas[1:]:
        if len(linha) <= max(idx_uf, idx_mun):
            continue
        uf = (linha[idx_uf] or "").strip().upper()
        municipio = _normalizar(linha[idx_mun])
        if ufs and uf not in ufs:
            continue
        if municipios_norm and municipio not in municipios_norm:
            continue
        saida.append(linha)

    buffer = io.StringIO()
    csv.writer(buffer, delimiter=";", lineterminator="\n").writerows(saida)
    return buffer.getvalue().encode("utf-8")


@task(name="sipeagro-baixar-area", retries=5, retry_delay_seconds=30)
def baixar_area(area: AreaDownload) -> bytes:
    url = area.url(C.CKAN_BASE_URL.value)
    try:
        resp = httpx.get(
            url, headers=C.HEADERS.value, timeout=C.HTTP_TIMEOUT.value,
            follow_redirects=True,
        )
    except httpx.HTTPError as exc:
        raise CsvIndisponivel(f"{area.area}: {exc.__class__.__name__}: {exc}") from exc
    if resp.status_code != 200:
        raise CsvIndisponivel(f"{area.area}: HTTP {resp.status_code} em {url}")
    return resp.content


@task(name="sipeagro-montar-e-enviar")
def montar_e_enviar(environment: str) -> dict:
    ufs = {C.UF.value.strip().upper()} if C.UF.value.strip() else set()
    municipios = set(C.MUNICIPIOS.value)

    run_id = f"sipeagro-{uuid.uuid4().hex[:12]}"
    buscou_em = datetime.now(UTC)

    itens: list[ItemLote] = []
    for area in C.AREAS.value:
        try:
            csv_bytes = baixar_area(area)
        except CsvIndisponivel as exc:
            log(f"sipeagro: falha ao baixar {area.area}: {exc}", level="warning")
            continue
        csv_filtrado = _filtrar_por_recorte(csv_bytes, ufs, municipios)
        itens.append(
            ItemLote(
                kind="csv", source_ref=area.area, conteudo={"area": area.area},
                blob_bytes=csv_filtrado, blob_content_type="text/csv",
            )
        )

    run = RunMeta(
        robo="sipeagro-flow", run_id=run_id, buscou_em=buscou_em,
        terminou_em=datetime.now(UTC),
    )
    resultado = enviar_lote(C.FONTE.value, run, itens, environment=environment)
    log(f"sipeagro: {len(itens)} área(s) enviada(s) ao COREVISA — {resultado}", level="info")
    return resultado
