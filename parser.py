"""Parser do nome da oportunidade GF2.

Nomes das opps seguem padrão variado:
  - "Ceesolar (158m) CPT"
  - "Ampère Energias (162m)CPT"
  - "Canadian Solar (UFV Alumínio (Ref.177) ? 4.41 MWp)"
  - "Lopes Energy - 50mwp"
  - "Ufv Gds 7 (Grampos)"
  - "Brazil Solution - Extrafruti Viana"

Estratégia: o primeiro "(" (quando existe) separa o cliente do miolo.
Metragem = primeiro número seguido de "m" / "mwp" / "mw" no nome.
Tipo = sufixo depois do último parêntese OU token final tipo CPT/2R/1R/Grampos/Abrigos.
"""
import re
from dataclasses import dataclass

TIPOS_CONHECIDOS = [
    "CPT-LO", "CPT", "2R", "1R", "3R", "Grampos", "Abrigos",
    "UFV", "Estrutura", "Solo", "Telhado", "Carport", "Tracker",
]


@dataclass
class NomeParsed:
    cliente: str
    tipo: str
    metragem: str  # guardado como texto pois vem em variações (158m, 4.41 MWp, 50mwp)
    potencia_kwp: float | None  # extraído quando der para converter


def _extrair_potencia_kwp(texto: str) -> float | None:
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(mwp|mw|kwp|kw)\b", texto, re.IGNORECASE)
    if m:
        val = float(m.group(1).replace(",", "."))
        unidade = m.group(2).lower()
        if "m" in unidade:
            return val * 1000  # MWp -> kWp
        return val
    m = re.search(r"\((\d+)\s*m\)", texto)  # "(158m)" = metragem em metros, não potência
    return None


def _extrair_metragem(texto: str) -> str:
    m = re.search(r"\((\d+)\s*m\)", texto)
    if m:
        return f"{m.group(1)}m"
    m = re.search(r"(\d+(?:[.,]\d+)?\s*(?:mwp|mw|kwp|kw))", texto, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return ""


def _extrair_tipo(texto: str) -> str:
    # Pega o sufixo após o último ")" se houver, senão últimos tokens
    apos_parentese = re.split(r"\)\s*", texto)
    sufixo = apos_parentese[-1].strip() if len(apos_parentese) > 1 else ""
    if sufixo:
        for t in TIPOS_CONHECIDOS:
            if re.search(rf"\b{re.escape(t)}\b", sufixo, re.IGNORECASE):
                return t
        # Se sobrou texto depois do último parêntese, usa como tipo bruto (limpo)
        sufixo_limpo = re.sub(r"[?\-\s]+$", "", sufixo).strip()
        if sufixo_limpo:
            return sufixo_limpo

    # Tenta achar tipo dentro do parêntese (ex: "Ufv Gds 7 (Grampos)")
    for t in TIPOS_CONHECIDOS:
        if re.search(rf"\b{re.escape(t)}\b", texto, re.IGNORECASE):
            return t
    return "—"


def _extrair_cliente(texto: str) -> str:
    # Antes do primeiro "(" ou " - "
    corte_par = texto.find("(")
    corte_hifen = texto.find(" - ")
    candidatos = [c for c in [corte_par, corte_hifen] if c > 0]
    if candidatos:
        cliente = texto[: min(candidatos)].strip()
    else:
        cliente = texto.strip()
    cliente = re.sub(r"\s+", " ", cliente)
    return cliente


def parse_nome_opp(nome: str) -> NomeParsed:
    if not nome:
        return NomeParsed(cliente="", tipo="—", metragem="", potencia_kwp=None)
    nome = nome.strip()
    return NomeParsed(
        cliente=_extrair_cliente(nome),
        tipo=_extrair_tipo(nome),
        metragem=_extrair_metragem(nome),
        potencia_kwp=_extrair_potencia_kwp(nome),
    )


if __name__ == "__main__":
    testes = [
        "Ceesolar (158m) CPT",
        "Ampère Energias (162m)CPT",
        "Canadian Solar (UFV Alumínio (Ref.177) ? 4.41 MWp)",
        "Lopes Energy - 50mwp",
        "Ufv Gds 7 (Grampos)",
        "Brazil Solution - Extrafruti Viana",
        "Clayton (360m) CPT-LO",
        "Solar Volt - LCM Energy (2844m) 2R",
    ]
    for t in testes:
        p = parse_nome_opp(t)
        print(f"{t!r:60s} -> cliente={p.cliente!r:25s} tipo={p.tipo!r:10s} metragem={p.metragem!r:10s} kwp={p.potencia_kwp}")
