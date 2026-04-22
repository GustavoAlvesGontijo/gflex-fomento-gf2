"""Cliente Salesforce slim para o Dashboard de Fomento GF2.

Copia o padrão de autenticação do [dashboard/salesforce_client.py] e expõe
apenas as queries necessárias para enriquecer as opps da GF2.
"""
import time as _time
import pandas as pd
import requests
import streamlit as st
from simple_salesforce import Salesforce

from config import (
    SF_CLIENT_ID, SF_CLIENT_SECRET, SF_REFRESH_TOKEN,
    SF_INSTANCE_URL, SF_DOMAIN, EMPRESA_SF, CACHE_TTL_SECONDS,
)

# Silencia warning de SSL quando verify=False
try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass


_sf_connection = None
_sf_token_time = 0
_SF_TOKEN_TTL = 5400  # 90 minutos


def _get_secret(key: str, fallback: str = "") -> str:
    try:
        return st.secrets["salesforce"][key]
    except Exception:
        return fallback


def _create_sf_connection() -> Salesforce:
    client_id = _get_secret("SF_CLIENT_ID", SF_CLIENT_ID)
    client_secret = _get_secret("SF_CLIENT_SECRET", SF_CLIENT_SECRET)
    refresh_token = _get_secret("SF_REFRESH_TOKEN", SF_REFRESH_TOKEN)
    domain = _get_secret("SF_DOMAIN", SF_DOMAIN)
    instance = _get_secret("SF_INSTANCE_URL", SF_INSTANCE_URL)
    token_url = f"https://{domain}.salesforce.com/services/oauth2/token"
    resp = requests.post(token_url, data={
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }, verify=False)
    resp.raise_for_status()
    tok = resp.json()
    session = requests.Session()
    session.verify = False
    return Salesforce(
        instance_url=tok.get("instance_url", instance),
        session_id=tok["access_token"],
        session=session,
    )


def get_sf_connection() -> Salesforce:
    global _sf_connection, _sf_token_time
    now = _time.time()
    if _sf_connection is None or (now - _sf_token_time) > _SF_TOKEN_TTL:
        _sf_connection = _create_sf_connection()
        _sf_token_time = now
    return _sf_connection


def _reset_sf_connection():
    global _sf_connection, _sf_token_time
    _sf_connection = None
    _sf_token_time = 0


def _query_to_df(soql: str) -> pd.DataFrame:
    try:
        sf = get_sf_connection()
        result = sf.query_all(soql)
    except Exception as e:
        if "INVALID_SESSION_ID" in str(e) or "Session expired" in str(e):
            _reset_sf_connection()
            sf = get_sf_connection()
            result = sf.query_all(soql)
        else:
            raise
    records = result.get("records", [])
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)
    if "attributes" in df.columns:
        df = df.drop(columns=["attributes"])
    for col in list(df.columns):
        if df[col].apply(lambda x: isinstance(x, dict)).any():
            nested = pd.json_normalize(df[col])
            nested.columns = [f"{col}.{c}" for c in nested.columns]
            if f"{col}.attributes" in nested.columns:
                nested = nested.drop(columns=[f"{col}.attributes"])
            df = df.drop(columns=[col]).join(nested)
    return df


def _escape_soql(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "\\'")


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def get_opps_gf2_acima(valor_min: float = 40000.0) -> pd.DataFrame:
    """Opps da GF2 acima do valor mínimo — traz Account, StageName, Amount,
    Owner, Código do Produto e Quantidade de Módulos."""
    soql = f"""
        SELECT Id, Name, Amount, StageName, CloseDate, CreatedDate,
               Account.Name, Owner.Name,
               Codigo_do_Produto_GF2__c, Quantidade_de_Modulos__c
        FROM Opportunity
        WHERE Empresa_Proprietaria__c = '{_escape_soql(EMPRESA_SF)}'
        AND Amount >= {valor_min}
    """
    return _query_to_df(soql)


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def get_line_items_por_opp(opp_ids: list[str]) -> pd.DataFrame:
    """OpportunityLineItem agregado por opp (total de itens, soma quantidade)."""
    if not opp_ids:
        return pd.DataFrame()
    ids_soql = ",".join([f"'{_escape_soql(i)}'" for i in opp_ids])
    soql = f"""
        SELECT OpportunityId, Product2.Name, Quantity, UnitPrice, TotalPrice
        FROM OpportunityLineItem
        WHERE OpportunityId IN ({ids_soql})
    """
    return _query_to_df(soql)


def testar_conexao() -> tuple[bool, str]:
    try:
        sf = get_sf_connection()
        sf.query("SELECT Id FROM Opportunity LIMIT 1")
        return True, "Conectado ao Salesforce"
    except Exception as e:
        return False, f"Falha: {e}"
