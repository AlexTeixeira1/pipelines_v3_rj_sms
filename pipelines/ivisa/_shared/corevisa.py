# -*- coding: utf-8 -*-
"""Cliente do lote do COREVISA (ADR 0001/0002).

Cada flow do IVISA busca na fonte e entrega um lote para
`POST /v1/ingestao/<fonte>/lote` — corpo e assinatura exatamente como
`corevisa/src/corevisa/api/v1/ingestao.py` espera. Nenhum flow parseia negócio:
`conteudo` carrega o JSON cru que o `parser.py`/`mapper.py` de cada fonte no
COREVISA já sabe interpretar.

Secrets (`COREVISA_URL`, `COREVISA_INGESTAO_LOTE_SECRET`) vêm do Infisical no
path `/ivisa`, nunca de arquivo do repo. Sem `COREVISA_URL` configurado, cai em
dry-run: grava o lote em `./out/<fonte>-lote.jsonl` em vez de postar — útil para
rodar flow localmente sem COREVISA no ar.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from pipelines.utils.infisical import get_secret
from pipelines.utils.logger import log

INFISICAL_PATH = "/ivisa"
SECRET_COREVISA_URL = "COREVISA_URL"
SECRET_LOTE = "COREVISA_INGESTAO_LOTE_SECRET"
HTTP_TIMEOUT = 60.0
LOTE_MAX = 500

_OUT_DIR = Path("./out")


@dataclass(frozen=True, slots=True)
class ItemLote:
    """Um item cru do lote — mesmo shape de `ItemLoteBruto` no COREVISA."""

    kind: str
    conteudo: dict[str, Any] = field(default_factory=dict)
    source_ref: str | None = None
    blob_bytes: bytes | None = None
    blob_content_type: str | None = None

    def como_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"kind": self.kind, "conteudo": self.conteudo}
        if self.source_ref is not None:
            d["source_ref"] = self.source_ref
        if self.blob_bytes is not None:
            d["blob_b64"] = base64.b64encode(self.blob_bytes).decode("ascii")
            d["blob_content_type"] = self.blob_content_type or "application/octet-stream"
        return d


@dataclass(frozen=True, slots=True)
class RunMeta:
    """Metadados do run — vira `ingestao_execucoes` no COREVISA."""

    robo: str
    run_id: str
    buscou_em: datetime | None = None
    terminou_em: datetime | None = None
    janela_inicio: datetime | None = None
    janela_fim: datetime | None = None

    def como_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"robo": self.robo, "run_id": self.run_id}
        if self.buscou_em is not None:
            d["buscou_em"] = self.buscou_em.isoformat()
        if self.terminou_em is not None:
            d["terminou_em"] = self.terminou_em.isoformat()
        if self.janela_inicio is not None or self.janela_fim is not None:
            d["janela"] = {
                "de": self.janela_inicio.isoformat() if self.janela_inicio else None,
                "ate": self.janela_fim.isoformat() if self.janela_fim else None,
            }
        return d


class LoteRejeitado(RuntimeError):
    """COREVISA recusou o lote (HMAC/HTTP != 2xx)."""


def _url_corevisa(environment: str) -> str:
    """URL do COREVISA no Infisical; vazia = dry-run."""
    try:
        return get_secret(
            path=INFISICAL_PATH, secret_name=SECRET_COREVISA_URL, environment=environment
        )
    except Exception:  # noqa: BLE001 — secret ausente cai em dry-run
        return ""


def _assinar(corpo: bytes, environment: str) -> str:
    segredo = get_secret(
        path=INFISICAL_PATH, secret_name=SECRET_LOTE, environment=environment
    )
    return hmac.new(segredo.encode(), corpo, hashlib.sha256).hexdigest()


def _dry_run(fonte: str, corpo: dict[str, Any]) -> dict[str, Any]:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    caminho = _OUT_DIR / f"{fonte}-lote.jsonl"
    with caminho.open("a", encoding="utf-8") as f:
        f.write(json.dumps(corpo, ensure_ascii=False) + "\n")
    n = len(corpo.get("registros") or [])
    log(f"corevisa.dry_run fonte={fonte} itens={n} arquivo={caminho}", level="info")
    return {"status": "dry_run", "itens": n}


def enviar_lote(
    fonte: str, run: RunMeta, itens: list[ItemLote], environment: str = "dev"
) -> dict[str, Any]:
    """Envia o lote para `POST /v1/ingestao/{fonte}/lote` em fatias de LOTE_MAX.
    Lote vazio não chama a rede. Sem `COREVISA_URL` no Infisical, grava em disco."""
    if not itens:
        log(f"corevisa.lote_vazio fonte={fonte} run_id={run.run_id}", level="info")
        return {"status": "vazio", "itens": 0}

    corevisa_url = _url_corevisa(environment)
    corpo_run = run.como_dict()

    if not corevisa_url:
        corpo = {"run": corpo_run, "registros": [i.como_dict() for i in itens]}
        return _dry_run(fonte, corpo)

    endpoint = f"{corevisa_url.rstrip('/')}/v1/ingestao/{fonte}/lote"
    resultados = []
    for i in range(0, len(itens), LOTE_MAX):
        fatia = itens[i : i + LOTE_MAX]
        corpo_bytes = json.dumps(
            {"run": corpo_run, "registros": [x.como_dict() for x in fatia]},
            ensure_ascii=False,
        ).encode("utf-8")
        resp = httpx.post(
            endpoint,
            content=corpo_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Ingestao-Signature": _assinar(corpo_bytes, environment),
            },
            timeout=HTTP_TIMEOUT,
        )
        if resp.status_code >= 400:
            raise LoteRejeitado(
                f"POST /v1/ingestao/{fonte}/lote -> {resp.status_code}: {resp.text[:500]}"
            )
        resultados.append(resp.json())
        log(
            f"corevisa.lote_enviado fonte={fonte} run_id={run.run_id} "
            f"fatia={i // LOTE_MAX} itens={len(fatia)} status={resp.status_code}",
            level="info",
        )
    return {"status": "enviado", "total": len(itens), "fatias": resultados}
