"""Carregamento do xlsx e enriquecimento com Salesforce."""
import unicodedata
import pandas as pd
import streamlit as st

from config import OPPORTUNITIES_XLSX, CACHE_TTL_SECONDS, POTENCIA_POR_MODULO_W
from parser import parse_nome_opp


def _norm(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return s.lower().strip()


def _norm_cliente(s: str) -> str:
    """Normaliza o cliente extraído do nome (antes do parêntese/hífen)."""
    s = _norm(s)
    # remove sufixos comuns que variam entre xlsx e SF
    for suf in [" energia", " solar", " ltda", " engenharia", " motors"]:
        if s.endswith(suf):
            s = s[: -len(suf)]
    return s.strip()


def _potencia_mwp_from_modulos(qtd: float | None) -> float | None:
    if qtd is None or pd.isna(qtd):
        return None
    return float(qtd) * POTENCIA_POR_MODULO_W / 1_000_000.0   # W → MWp


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def carregar_xlsx() -> pd.DataFrame:
    df = pd.read_excel(OPPORTUNITIES_XLSX)
    df = df.rename(columns={
        "Nome da oportunidade": "nome",
        "Total Absoluto": "valor",
        "Proprietário da oportunidade": "proprietario",
        "Data de criação": "data_criacao",
    })
    df = df.dropna(subset=["nome", "valor"]).reset_index(drop=True)
    parsed = df["nome"].apply(parse_nome_opp)
    df["cliente"] = [p.cliente for p in parsed]
    df["tipo_parser"] = [p.tipo for p in parsed]
    df["metragem_parser"] = [p.metragem for p in parsed]
    df["data_criacao"] = pd.to_datetime(df["data_criacao"], errors="coerce")
    # Campos que virão do SF (placeholders)
    df["sf_id"] = None
    df["sf_conta"] = None
    df["sf_fase"] = None
    df["sf_amount"] = None
    df["codigo_produto"] = None
    df["qtd_modulos"] = None
    df["potencia_mwp"] = None
    return df


def enriquecer_com_sf(df_xlsx: pd.DataFrame) -> pd.DataFrame:
    """Casa cada opp do xlsx com uma opp do SF.

    Estratégia em 3 níveis:
      1) Match exato por nome normalizado.
      2) Match por (cliente_normalizado, Amount) com tolerância de R$ 1 (arredondamento).
      3) Se falhar, deixa campos SF como None.
    """
    from salesforce_client import get_opps_gf2_acima

    df = df_xlsx.copy()
    try:
        sf_df = get_opps_gf2_acima(valor_min=30000.0)
    except Exception as e:
        st.warning(f"Não foi possível enriquecer com Salesforce: {e}")
        return df

    if sf_df.empty:
        return df

    sf_df = sf_df.rename(columns={
        "Id": "sf_id",
        "Name": "sf_nome",
        "Amount": "sf_amount",
        "StageName": "sf_fase",
        "Account.Name": "sf_conta",
        "Owner.Name": "sf_owner",
        "Codigo_do_Produto_GF2__c": "codigo_produto",
        "Quantidade_de_Modulos__c": "qtd_modulos",
    })
    sf_df["_nome_norm"] = sf_df["sf_nome"].astype(str).apply(_norm)
    sf_df["_cliente_norm"] = sf_df["sf_nome"].astype(str).apply(
        lambda n: _norm_cliente(n.split("(")[0].split(" - ")[0])
    )

    # Index por nome para match direto
    idx_por_nome = {row["_nome_norm"]: row for _, row in sf_df.iterrows()}

    resultados = []
    for _, row in df.iterrows():
        nome_norm = _norm(row["nome"])
        match = idx_por_nome.get(nome_norm)
        if match is None:
            cliente_norm = _norm_cliente(row["cliente"])
            valor = float(row["valor"])
            candidatos = sf_df[
                (sf_df["_cliente_norm"] == cliente_norm)
                & (sf_df["sf_amount"].sub(valor).abs() <= max(1.0, abs(valor) * 0.001))
            ]
            if not candidatos.empty:
                match = candidatos.iloc[0]

        if match is not None:
            qtd = match.get("qtd_modulos")
            resultados.append({
                "sf_id": match.get("sf_id"),
                "sf_conta": match.get("sf_conta"),
                "sf_fase": match.get("sf_fase"),
                "sf_amount": match.get("sf_amount"),
                "codigo_produto": match.get("codigo_produto"),
                "qtd_modulos": qtd,
                "potencia_mwp": _potencia_mwp_from_modulos(qtd),
            })
        else:
            resultados.append({
                "sf_id": None, "sf_conta": None, "sf_fase": None, "sf_amount": None,
                "codigo_produto": None, "qtd_modulos": None, "potencia_mwp": None,
            })

    enriquecido = pd.DataFrame(resultados, index=df.index)
    for col in ["sf_id", "sf_conta", "sf_fase", "sf_amount",
                "codigo_produto", "qtd_modulos", "potencia_mwp"]:
        df[col] = enriquecido[col]
    return df
