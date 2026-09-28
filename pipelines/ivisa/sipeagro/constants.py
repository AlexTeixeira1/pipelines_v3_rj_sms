# -*- coding: utf-8 -*-
"""Constantes do flow SIPEAGRO.

As 9 áreas do dataset SIPEAGRO no Portal de Dados Abertos do MAPA (CKAN) e o
recorte IVISA (UF + município). O mapeamento de colunas/parsing fica só no
COREVISA (`infra/normalizacao/sipeagro/`) — aqui é só o que baixar e recortar.
"""

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class AreaDownload:
    area: str
    resource_id: str
    arquivo: str

    def url(self, base_url: str) -> str:
        base = base_url.rstrip("/")
        return (
            f"{base}/dataset/{constants.DATASET_ID.value}"
            f"/resource/{self.resource_id}/download/{self.arquivo}"
        )


class constants(Enum):
    FONTE = "sipeagro"
    CKAN_BASE_URL = "https://dados.agricultura.gov.br"
    HTTP_TIMEOUT = 60.0
    DATASET_ID = "52a01565-72d6-410e-b21b-64035831a7be"

    # Recorte IVISA-RIO — o dataset é Brasil inteiro
    UF = "RJ"
    MUNICIPIOS = ["Rio de Janeiro"]

    # dados.agricultura.gov.br devolve 403 para User-Agent não-browser
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Accept": "text/csv,application/csv,*/*",
    }

    AREAS = [
        AreaDownload(
            "ALIMENTACAO_ANIMAL", "378b184b-67bd-48fa-9901-17bb7a0700fb",
            "sipeagroalimentacaoanimal.csv",
        ),
        AreaDownload(
            "FERTILIZANTES", "e0bbc9d5-f161-448b-a6d4-c7beb312ec33",
            "sipeagrofertilizante.csv",
        ),
        AreaDownload(
            "PRODUTO_VETERINARIO", "7ce5fac0-9c8f-4e14-82d9-6deab9b5e2e9",
            "sipeagroprodutoveterinario.csv",
        ),
        AreaDownload(
            "AVES_REPRODUCAO", "837ed03c-e030-4304-8028-359224d6811b",
            "sipeagroavesreproducao.csv",
        ),
        AreaDownload(
            "MATERIAL_MULTIPLICACAO_ANIMAL", "aacf761c-d6b2-4f11-975f-11a736e547b9",
            "sipeagromultiplicacaoanimal.csv",
        ),
        AreaDownload(
            "AVIACAO_AGRICOLA_REGISTRO", "fac50de6-d4c4-4b47-bac9-5b144de448c9",
            "sipeagroaviacaoagricolaregistro.csv",
        ),
        AreaDownload(
            "AVIACAO_AGRICOLA_AUTORIZACAO", "0626b768-7a83-49ba-a0c7-2365880e383d",
            "sipeagroaviacaoagricolaautorizacao.csv",
        ),
        AreaDownload(
            "QUALIDADE_VEGETAL", "e9368a44-4c15-4218-ad96-1a62052ff2c6",
            "sipeagroqualidadevegetal.csv",
        ),
        AreaDownload(
            "VINHOS_E_BEBIDAS", "8ef7a4fc-f9d9-495b-b3ae-a2ffe931ff82",
            "sipeagrovinhosebebidas.csv",
        ),
    ]
