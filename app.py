"""Dashboard Fomento à Produção (Risco Sacado) — GF2 Soluções.

3 abas:
  1) Tabela & Totais — cards agregados, cards por categoria, tabela
  2) Fluxo por pedido — header em cards + matriz dia × categoria + gráfico
  3) Comparar pedidos — filtros + cards multi-selecionáveis + MATRIZ agregada

Sidebar: categorias (% + prazo fornecedor + dia de pagamento direto), opção de
recebimento, prazo entrega, taxa do fundo. Tudo persiste em params.json.
"""
from __future__ import annotations
import copy

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import (
    COR_PRIMARIA, COR_POSITIVO, COR_NEGATIVO, COR_NEUTRO,
    OPCOES_RECEBIMENTO, PRAZO_ENTREGA_CLIENTE_DEFAULT,
    CATEGORIAS_CUSTO_DEFAULT,
)
from data import carregar_xlsx, enriquecer_com_sf
from fomento import calcular_resumo
from timeline import gerar_fluxo, somar_fluxos, LINHA_QUITACAO
from params_store import (
    load_params, save_params, get_override_opp, set_override_opp,
    categorias_para_opp,
)


st.set_page_config(
    page_title="Fomento GF2",
    page_icon="💠",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ========================================
# AUTENTICAÇÃO — acesso por senha
# ========================================
def check_password():
    try:
        correct = st.secrets["app"]["password"]
    except Exception:
        import os as _os
        correct = _os.getenv("APP_PASSWORD", "")
        if not correct:
            st.error("Senha não configurada. Configure st.secrets ou APP_PASSWORD.")
            st.stop()
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if st.session_state.authenticated:
        return True
    st.markdown("""
<div style="max-width:420px;margin:80px auto;text-align:center">
<div style="background:#004A9D;padding:24px;border-radius:14px;margin-bottom:24px">
<h1 style="color:white;margin:0;font-size:1.6rem">💠 Fomento GF2</h1>
<p style="color:#cfe0f5;margin:6px 0 0 0;font-size:0.9rem">Análise de pedidos · Acesso Restrito</p>
</div>
</div>
""", unsafe_allow_html=True)
    pwd = st.text_input("Senha de acesso", type="password", key="pwd_input")
    if pwd:
        if pwd == correct:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Senha incorreta")
    return False


if not check_password():
    st.stop()

st.markdown(f"""
<style>
[data-testid="stHeader"] {{ background:{COR_PRIMARIA}; }}
[data-testid="stSidebar"] {{ background:#f4f6fa; }}
h1, h2, h3 {{ color:{COR_PRIMARIA}; }}
[data-testid="stMetricValue"] {{ font-size:1.3rem; font-weight:700; color:{COR_PRIMARIA}; }}
[data-testid="stMetricLabel"] {{ font-size:0.7rem; font-weight:600;
    text-transform:uppercase; letter-spacing:0.5px; color:#555; }}
[data-testid="stDataFrame"] th {{ background:{COR_PRIMARIA} !important; color:white !important;
    font-weight:600; font-size:0.82rem !important;
    text-transform:uppercase; letter-spacing:0.3px; }}
[data-testid="stDataFrame"] td {{ font-size:0.9rem !important; }}
.card-hero {{
    background:linear-gradient(135deg, {COR_PRIMARIA} 0%, #0066C2 100%);
    padding:24px 28px; border-radius:14px; margin-bottom:18px; color:white;
}}
.card-hero h1 {{ color:white; margin:0; font-size:1.6rem; }}
.card-hero p  {{ color:#cfe0f5; margin:6px 0 0 0; font-size:0.9rem; }}
.matriz table {{ border-collapse:collapse; width:100%; font-size:0.82rem; }}
.matriz th, .matriz td {{ border:1px solid #e5e7eb; padding:5px 8px; text-align:right; }}
.matriz th {{ background:{COR_PRIMARIA}; color:white; text-align:center; font-weight:600; }}
.matriz td.cat {{ text-align:left; font-weight:600; color:#1a1a2e; background:#f8fafc; }}
.matriz tr.quitacao td {{ background:#fef3c7; font-weight:600; }}
.matriz tr.resumo td {{ background:#eef2ff; font-weight:600; }}
.matriz tr.final td {{ background:#d1fae5; font-weight:700; }}
.cat-card {{
    background:#fff; border:1px solid #e5e7eb; border-radius:10px;
    padding:10px 14px; margin:0 0 8px 0;
}}
.cat-card .cat-nome {{ font-size:0.72rem; font-weight:600; text-transform:uppercase;
    color:#555; letter-spacing:0.5px; }}
.cat-card .cat-valor {{ font-size:1.05rem; font-weight:700; color:{COR_PRIMARIA}; }}
.cat-card .cat-pct {{ font-size:0.78rem; color:#6B7280; }}
.opp-card-min {{
    border:1px solid #e5e7eb; border-radius:10px; padding:10px 12px;
    background:#fff; margin-bottom:8px; border-left:3px solid {COR_PRIMARIA};
}}
.opp-card-min .opc-titulo {{ font-size:0.85rem; color:#1a1a2e; font-weight:600; margin:0; }}
.opp-card-min .opc-linha {{ display:flex; justify-content:space-between;
    font-size:0.78rem; color:#333; padding:1px 0; }}
</style>
""", unsafe_allow_html=True)


# --- formatação BR ---
def _fmt_brl(v, sinal=True) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if not sinal:
        return f"R$ {s}"
    return f"R$ {s}" if v >= 0 else f"-R$ {s}"


def _fmt_num(v, casas=0) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    fmt = f"{{:,.{casas}f}}"
    return fmt.format(v).replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_pct(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return f"{v:.1f}%".replace(".", ",")


def _fmt_mwp(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return f"{_fmt_num(v, casas=3)} MWp"


def _color(v: float) -> str:
    return COR_POSITIVO if v >= 0 else COR_NEGATIVO


# --- helpers de cálculo ---
def _effective_params(params):
    """Normaliza params garantindo chaves esperadas."""
    params.setdefault("dias_pagamento", {})
    params.setdefault("overrides_opp", {})
    return params


def _calc_fluxo_row(row, params):
    cats = categorias_para_opp(params, row["nome"])
    ovr = get_override_opp(params, row["nome"])
    op_key_opp = ovr.get("opcao", params["opcao_recebimento_default"])
    prazo_opp = int(ovr.get("prazo_entrega_cliente", params["prazo_entrega_cliente"]))
    opcao = OPCOES_RECEBIMENTO[op_key_opp]

    # dias pagamento: global → override da opp
    dias_pgto = dict(params.get("dias_pagamento", {}))
    dias_pgto.update(ovr.get("dias_pagamento", {}))

    fluxo = gerar_fluxo(
        valor=row["valor"], categorias=cats,
        opcao_recebimento=opcao, prazo_entrega_cliente=prazo_opp,
        taxa_mes=params["taxa_juros_mensal"],
        dias_pagamento_override=dias_pgto,
    )
    return fluxo, cats, op_key_opp, prazo_opp


# --- load data ---
try:
    df = carregar_xlsx()
except Exception as e:
    st.error(f"Não foi possível ler o xlsx: {e}")
    st.stop()

params = _effective_params(load_params())


# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    st.markdown("### Fomento GF2")
    st.caption("Parâmetros editáveis. Clique **💾 Salvar** para persistir em `params.json`.")

    st.markdown("#### Taxa e prazo da operação")
    params["taxa_juros_mensal"] = st.number_input(
        "Taxa do fundo (% ao mês sobre aporte)",
        min_value=0.0, max_value=20.0, step=0.1,
        value=float(params.get("taxa_juros_mensal", 1.5)),
        help="Conta escrow. Juros lineares × dias de operação.",
    )
    params["prazo_entrega_cliente"] = st.number_input(
        "Prazo de entrega ao cliente (dias corridos)",
        min_value=1, max_value=365, step=1,
        value=int(params.get("prazo_entrega_cliente", PRAZO_ENTREGA_CLIENTE_DEFAULT)),
        help="D+X em que a GF2 entrega o pedido.",
    )
    prazo_cli = int(params["prazo_entrega_cliente"])

    st.markdown("#### Condição de recebimento")
    op_key = st.radio(
        "Opção default",
        options=list(OPCOES_RECEBIMENTO.keys()),
        format_func=lambda k: OPCOES_RECEBIMENTO[k]["label"],
        index=list(OPCOES_RECEBIMENTO.keys()).index(
            params.get("opcao_recebimento_default", "op1")),
        key="opcao_radio",
    )
    params["opcao_recebimento_default"] = op_key

    st.markdown("#### Categorias de custo")
    st.caption("% do faturamento · dia de pagamento (D+)")
    for nome, conf_default in CATEGORIAS_CUSTO_DEFAULT.items():
        conf = params["categorias_custo"].setdefault(nome, copy.deepcopy(conf_default))

        # dia auto default — respeita dia_pagamento_default (ex: Aço+Galv = 1)
        if "dia_pagamento_default" in conf:
            auto_dia = int(conf["dia_pagamento_default"])
        elif conf.get("tipo") == "insumo":
            auto_dia = max(0, prazo_cli - int(conf.get("prazo_entrega_fornecedor", 0)))
        elif conf.get("tipo") == "operacional":
            auto_dia = prazo_cli
        else:
            auto_dia = None  # imposto é proporcional

        dia_atual = params["dias_pagamento"].get(nome, auto_dia)
        dia_label = f" · paga D+{dia_atual}" if auto_dia is not None and dia_atual is not None else ""
        with st.expander(f"**{nome}** — {conf['pct']:.1f}%{dia_label}", expanded=False):
            conf["pct"] = st.number_input(
                "% do faturamento", min_value=0.0, max_value=100.0, step=0.5,
                value=float(conf["pct"]), key=f"cat_pct_{nome}",
            )
            if conf.get("tipo") == "insumo":
                conf["prazo_entrega_fornecedor"] = st.number_input(
                    "Prazo do fornecedor (dias até chegar)",
                    min_value=0, max_value=120, step=1,
                    value=int(conf.get("prazo_entrega_fornecedor", 0)),
                    key=f"cat_prazo_{nome}",
                )
                # recalcula auto se NÃO tiver dia_pagamento_default fixo
                if "dia_pagamento_default" not in conf:
                    auto_dia = max(0, prazo_cli - int(conf["prazo_entrega_fornecedor"]))

            if auto_dia is not None:
                dia_input = st.number_input(
                    f"Dia de pagamento (auto: D+{auto_dia})",
                    min_value=0, max_value=365, step=1,
                    value=int(dia_atual) if dia_atual is not None else int(auto_dia),
                    key=f"dia_{nome}",
                    help="Default é calculado automaticamente. Coloque um valor diferente para forçar outro dia.",
                )
                if int(dia_input) == int(auto_dia):
                    params["dias_pagamento"].pop(nome, None)
                else:
                    params["dias_pagamento"][nome] = int(dia_input)
            else:
                st.caption("Imposto: distribuído proporcional às parcelas recebidas.")

    custos_total = sum(c["pct"] for c in params["categorias_custo"].values())
    st.caption(f"**Soma custos: {_fmt_num(custos_total, 1)}%** · Margem implícita: {_fmt_num(100 - custos_total, 1)}%")

    st.markdown("---")
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        if st.button("💾 Salvar globais", width="stretch"):
            save_params(params)
            st.success("Parâmetros globais salvos!")
    with col_s2:
        if st.button("🔄 Recarregar", width="stretch"):
            carregar_xlsx.clear()
            st.rerun()

    st.markdown("---")
    sf_on = st.toggle(
        "Enriquecer com Salesforce",
        value=True,
        help="Traz Código do Produto, Quantidade de Módulos (potência), Conta e Fase.",
    )


# --- enriquecimento SF ---
if sf_on:
    with st.spinner("Consultando Salesforce..."):
        df = enriquecer_com_sf(df)


# --- filtros globais (sidebar) ---
with st.sidebar:
    st.markdown("#### Filtros globais")
    owners = ["Todos"] + sorted(df["proprietario"].dropna().unique().tolist())
    owner_f = st.selectbox("Proprietário", owners, key="f_owner")
    codigos_presentes = sorted([c for c in df["codigo_produto"].dropna().unique() if c])
    codigos_f = ["Todos"] + codigos_presentes if codigos_presentes else ["Todos"]
    codigo_f = st.selectbox("Código do Produto", codigos_f, key="f_codigo")
    val_min, val_max = float(df["valor"].min()), float(df["valor"].max())
    faixa = st.slider(
        "Faixa de valor (R$)",
        min_value=val_min, max_value=val_max,
        value=(val_min, val_max), step=1000.0,
    )


df_f = df.copy()
if owner_f != "Todos":
    df_f = df_f[df_f["proprietario"] == owner_f]
if codigo_f != "Todos":
    df_f = df_f[df_f["codigo_produto"] == codigo_f]
df_f = df_f[(df_f["valor"] >= faixa[0]) & (df_f["valor"] <= faixa[1])]


def _resumo_opp(row, params) -> dict:
    fluxo, cats, op_key_opp, prazo_opp = _calc_fluxo_row(row, params)
    resumo = calcular_resumo(row["valor"], cats)
    return {
        "nome": row["nome"], "cliente": row["cliente"],
        "codigo": row.get("codigo_produto") or "—",
        "potencia_mwp": row.get("potencia_mwp"),
        "qtd_modulos": row.get("qtd_modulos"),
        "proprietario": row["proprietario"],
        "data_criacao": row["data_criacao"],
        "sf_conta": row.get("sf_conta"), "sf_fase": row.get("sf_fase"),
        "valor": resumo.valor, "custo_rs": resumo.custo_total,
        "margem_rs": resumo.margem_bruta, "margem_pct": resumo.margem_bruta_pct,
        "opcao": op_key_opp, "prazo_cliente": prazo_opp,
        "dias": fluxo.dias_operacao, "aporte": fluxo.aporte,
        "juros_fundo": fluxo.juros_fundo, "resultado_gf2": fluxo.resultado_gf2,
        "resultado_gf2_pct": fluxo.resultado_gf2_pct,
        "custos_categoria": dict(fluxo.matriz.drop(LINHA_QUITACAO, errors="ignore")
                                 .loc[[c for c in fluxo.matriz.index
                                       if c not in ("VALOR DA PROPOSTA", LINHA_QUITACAO)]]
                                 .sum(axis=1).abs().to_dict()),
    }


calc_df = pd.DataFrame([_resumo_opp(r, params) for _, r in df_f.iterrows()])


# --- HERO ---
st.markdown(f"""
<div class="card-hero">
  <h1>Fomento à Produção — GF2 Soluções</h1>
  <p>Análise pedido a pedido · Risco sacado · Dias corridos a partir do fechamento (D+0) · Conta escrow</p>
</div>
""", unsafe_allow_html=True)

if calc_df.empty:
    st.info("Nenhuma opp no filtro atual.")
    st.stop()

_OPCAO_CURTA = {"op1": "50/25/25", "op2": "30/70", "op3": "50/50"}


# ============================================================
# ABAS
# ============================================================
tab_tabela, tab_fluxo, tab_compara, tab_ajuda = st.tabs(
    ["📊 Tabela & Totais", "🧾 Fluxo por pedido", "🔀 Comparar pedidos", "ℹ️ Como funciona"]
)


# ============================================================
# ABA 1 — Tabela & Totais
# ============================================================
with tab_tabela:
    tot_valor = calc_df["valor"].sum()
    tot_margem = calc_df["margem_rs"].sum()
    tot_aporte = calc_df["aporte"].sum()
    tot_juros = calc_df["juros_fundo"].sum()
    tot_result = calc_df["resultado_gf2"].sum()

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Oportunidades", _fmt_num(len(calc_df)))
    c2.metric("Valor total", _fmt_brl(tot_valor, sinal=False))
    c3.metric("Margem", _fmt_brl(tot_margem),
              delta=f"{_fmt_num(tot_margem/tot_valor*100, 1)}% do valor")
    c4.metric("Aporte (exposição)", _fmt_brl(tot_aporte, sinal=False))
    c5.metric("Juros ao fundo", _fmt_brl(tot_juros),
              delta=f"{_fmt_num(params['taxa_juros_mensal'], 2)}%/mês")
    c6.metric("Resultado GF2", _fmt_brl(tot_result),
              delta=f"{_fmt_num(tot_result/tot_valor*100, 1)}% do valor")

    # --- cards por categoria (gastos agregados) ---
    st.markdown("#### Gastos por categoria (agregado do filtro)")
    totais_cat = {}
    for _, r in df_f.iterrows():
        cats = categorias_para_opp(params, r["nome"])
        for nome, conf in cats.items():
            if conf.get("tipo") == "imposto":
                continue
            totais_cat[nome] = totais_cat.get(nome, 0.0) + r["valor"] * float(conf.get("pct", 0)) / 100.0
    # imposto sempre tem linha
    imp_total = sum(r["valor"] * float(params["categorias_custo"].get("Imposto", {}).get("pct", 0)) / 100.0
                    for _, r in df_f.iterrows())
    totais_cat["Imposto"] = imp_total

    # ordem fixa para exibição
    ordem_cats = ["Aço+Galvanização", "Alumínio", "Insumos Produção",
                  "Mão de Obra", "ADM/Comercial", "Frete", "Imposto"]
    cols_cat = st.columns(len(ordem_cats))
    for col, nome in zip(cols_cat, ordem_cats):
        val = totais_cat.get(nome, 0.0)
        pct = (val / tot_valor * 100.0) if tot_valor else 0.0
        pct_conf = float(params["categorias_custo"].get(nome, {}).get("pct", 0))
        with col:
            st.markdown(
                f"""<div class="cat-card">
                    <div class="cat-nome">{nome}</div>
                    <div class="cat-valor">{_fmt_brl(val, sinal=False)}</div>
                    <div class="cat-pct">{_fmt_num(pct_conf, 1)}% do faturamento</div>
                </div>""",
                unsafe_allow_html=True,
            )

    # --- tabela principal ---
    st.markdown("### Oportunidades")

    display = pd.DataFrame({
        "Cliente": calc_df["cliente"],
        "Código": calc_df["codigo"],
        "Potência (MWp)": calc_df["potencia_mwp"],
        "Módulos": calc_df["qtd_modulos"],
        "Proprietário": calc_df["proprietario"],
        "Valor": calc_df["valor"],
        "Custo": calc_df["custo_rs"],
        "Margem": calc_df["margem_rs"],
        "Margem %": calc_df["margem_pct"],
        "Recebimento": calc_df["opcao"].map(_OPCAO_CURTA).fillna(calc_df["opcao"]),
        "Entrega D+": calc_df["prazo_cliente"],
        "Dias op.": calc_df["dias"],
        "Aporte": calc_df["aporte"],
        "Juros fundo": calc_df["juros_fundo"],
        "Resultado GF2": calc_df["resultado_gf2"],
        "Res. GF2 %": calc_df["resultado_gf2_pct"],
        "Conta SF": calc_df["sf_conta"],
        "Fase SF": calc_df["sf_fase"],
        "Criada em": calc_df["data_criacao"],
        "Nome opp": calc_df["nome"],
    }).sort_values("Valor", ascending=False)

    def _fmt_brl_s(v): return _fmt_brl(v) if pd.notna(v) else "—"
    def _fmt_brl_u(v): return _fmt_brl(v, sinal=False) if pd.notna(v) else "—"
    def _fmt_pct_s(v): return _fmt_pct(v) if pd.notna(v) else "—"
    def _fmt_int(v):   return _fmt_num(v, 0) if pd.notna(v) else "—"
    def _fmt_mwp_s(v): return _fmt_mwp(v) if pd.notna(v) else "—"

    styler = display.style.format({
        "Valor": _fmt_brl_u, "Custo": _fmt_brl_u, "Aporte": _fmt_brl_u,
        "Margem": _fmt_brl_s, "Juros fundo": _fmt_brl_s, "Resultado GF2": _fmt_brl_s,
        "Margem %": _fmt_pct_s, "Res. GF2 %": _fmt_pct_s,
        "Módulos": _fmt_int, "Entrega D+": _fmt_int, "Dias op.": _fmt_int,
        "Potência (MWp)": _fmt_mwp_s,
        "Criada em": lambda d: d.strftime("%d/%m/%Y") if pd.notna(d) else "—",
    }, na_rep="—")

    st.dataframe(styler, width="stretch", height=520, hide_index=True)

    csv_bytes = display.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")
    st.download_button("⬇️ Baixar CSV", data=csv_bytes,
                       file_name="fomento_gf2.csv", mime="text/csv")


# ============================================================
# ABA 2 — Fluxo por pedido
# ============================================================
with tab_fluxo:
    sel = st.selectbox(
        "Selecione uma opp",
        options=calc_df.sort_values("valor", ascending=False)["nome"].tolist(),
        key="opp_sel_fluxo",
    )
    linha = calc_df[calc_df["nome"] == sel].iloc[0]
    row_raw = df_f[df_f["nome"] == sel].iloc[0]
    fluxo, cats_opp, op_key_opp, prazo_opp = _calc_fluxo_row(row_raw, params)

    # === Header em cards ===
    c_id1, c_id2, c_id3, c_id4 = st.columns([1.2, 2, 1, 1])
    c_id1.metric("Cliente", linha["cliente"] or "—")
    c_id2.metric("Pedido",
                 linha["nome"][:38] + ("…" if len(linha["nome"]) > 38 else ""))
    c_id3.metric("Código produto", linha["codigo"] or "—")
    c_id4.metric("Valor do pedido", _fmt_brl(linha["valor"], sinal=False))

    c_id5, c_id6, c_id7 = st.columns(3)
    c_id5.metric("Potência", _fmt_mwp(linha["potencia_mwp"]),
                 delta=f"{_fmt_num(linha['qtd_modulos'], 0)} módulos" if pd.notna(linha["qtd_modulos"]) else None)
    c_id6.metric("Recebimento cliente", _OPCAO_CURTA.get(op_key_opp, op_key_opp))
    c_id7.metric("Entrega", f"D+{prazo_opp}")

    if linha.get("sf_conta"):
        st.caption(f"Conta SF: **{linha['sf_conta']}** · Fase SF: **{linha.get('sf_fase', '—')}** · Proprietário: **{linha['proprietario']}**")

    # === Métricas do fundo ===
    st.markdown("##### Resultado financeiro")
    # dia do pior momento (onde acumulado sem aporte = mínimo)
    try:
        dia_pior = int(fluxo.acumulado.idxmin().replace("D+", "")) if not fluxo.acumulado.empty else 0
    except Exception:
        dia_pior = 0

    c_m1, c_m2, c_m3, c_m4, c_m5 = st.columns(5)
    c_m1.metric("Margem contribuição", _fmt_brl(fluxo.margem_contribuicao),
                delta=f"{_fmt_num(fluxo.margem_pct, 2)}%")
    c_m2.metric("Aporte (escrow)", _fmt_brl(fluxo.aporte, sinal=False),
                delta=f"pior momento: D+{dia_pior}", delta_color="off")
    c_m3.metric("Dias operação", f"{fluxo.dias_operacao}",
                delta=f"entrega D+{prazo_opp}", delta_color="off")
    c_m4.metric(f"Juros ao fundo ({_fmt_num(fluxo.taxa_mes, 2)}%/mês)",
                _fmt_brl(fluxo.juros_fundo, sinal=False))
    c_m5.metric("Resultado líquido GF2", _fmt_brl(fluxo.resultado_gf2),
                delta=f"{_fmt_num(fluxo.resultado_gf2_pct, 2)}% do valor")

    # === Matriz ===
    st.markdown("#### Matriz de fluxo de caixa (dia × categoria)")
    parcelas_txt = " · ".join(
        [f"D+{d}: {_fmt_num(pct, 0)}%" for pct, d in OPCOES_RECEBIMENTO[op_key_opp]["parcelas"]]
    )
    st.caption(
        f"Parcelas do cliente: {parcelas_txt} · "
        f"Quitação do fundo no último dia: {_fmt_brl(fluxo.aporte + fluxo.juros_fundo, sinal=False)}"
    )

    def _fmt_cell(v: float) -> str:
        if v is None or (isinstance(v, float) and pd.isna(v)) or v == 0:
            return ""
        cor = COR_POSITIVO if v > 0 else COR_NEGATIVO
        return f"<span style='color:{cor}'>{_fmt_brl(v)}</span>"

    def _render_matriz(matriz, fluxo_dia, acumulado, acumulado_com_aporte) -> str:
        dias_cols = list(matriz.columns)
        html = "<table class='matriz'><thead><tr><th style='text-align:left'>Categoria</th>"
        for d in dias_cols:
            html += f"<th>{d}</th>"
        html += "</tr></thead><tbody>"
        for cat, row in matriz.iterrows():
            classe = " class='quitacao'" if cat == LINHA_QUITACAO else ""
            html += f"<tr{classe}><td class='cat'>{cat}</td>"
            for d in dias_cols:
                html += f"<td>{_fmt_cell(row[d])}</td>"
            html += "</tr>"
        html += "<tr class='resumo'><td class='cat'>Fluxo do dia</td>"
        for d in dias_cols:
            html += f"<td>{_fmt_cell(fluxo_dia[d])}</td>"
        html += "</tr><tr class='resumo'><td class='cat'>Acumulado (sem aporte)</td>"
        for d in dias_cols:
            html += f"<td>{_fmt_cell(acumulado[d])}</td>"
        html += "</tr><tr class='final'><td class='cat'>Acumulado (com aporte)</td>"
        for d in dias_cols:
            html += f"<td>{_fmt_cell(acumulado_com_aporte[d])}</td>"
        html += "</tr></tbody></table>"
        return html

    st.markdown(_render_matriz(fluxo.matriz, fluxo.fluxo_dia,
                               fluxo.acumulado, fluxo.acumulado_com_aporte),
                unsafe_allow_html=True)

    # === Gráfico ===
    st.markdown("#### Evolução do caixa")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=fluxo.dias, y=fluxo.acumulado.values, name="Sem aporte",
        mode="lines+markers",
        line=dict(color=COR_NEGATIVO, width=2, dash="dash"),
    ))
    fig.add_trace(go.Scatter(
        x=fluxo.dias, y=fluxo.acumulado_com_aporte.values, name="Com aporte",
        mode="lines+markers",
        line=dict(color=COR_POSITIVO, width=3),
        fill="tozeroy", fillcolor="rgba(31,138,46,0.08)",
    ))
    fig.add_hline(y=0, line=dict(color="#999", width=1, dash="dot"))
    fig.add_hline(
        y=-fluxo.aporte, line=dict(color=COR_NEGATIVO, width=1, dash="dot"),
        annotation_text=f"Exposição máx: {_fmt_brl(fluxo.aporte, sinal=False)}",
        annotation_position="bottom right",
    )
    fig.update_layout(
        height=340, margin=dict(l=20, r=20, t=30, b=40),
        xaxis_title="Dias corridos (D+)",
        yaxis_title="Saldo acumulado (R$)",
        plot_bgcolor="white", hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_xaxes(gridcolor="#eee", zeroline=False)
    fig.update_yaxes(gridcolor="#eee", zeroline=False, tickprefix="R$ ", tickformat=",.0f")
    st.plotly_chart(fig, width="stretch")

    # === Ajustes por opp ===
    st.markdown("#### Ajustes para este pedido")
    st.caption(
        "Sobrepõem os parâmetros globais **apenas para esta opp**. "
        "Salva no `params.json` em `overrides_opp[nome_opp]`."
    )
    ovr = get_override_opp(params, sel)
    col_ov1, col_ov2, col_ov3 = st.columns(3)
    with col_ov1:
        op_opp = st.selectbox(
            "Opção de recebimento",
            options=list(OPCOES_RECEBIMENTO.keys()),
            format_func=lambda k: OPCOES_RECEBIMENTO[k]["label"],
            index=list(OPCOES_RECEBIMENTO.keys()).index(op_key_opp),
            key=f"opp_opc_{sel}",
        )
    with col_ov2:
        prazo_opp_new = st.number_input(
            "Prazo entrega cliente (dias)",
            min_value=1, max_value=365, step=1,
            value=prazo_opp, key=f"opp_prazo_{sel}",
        )
    with col_ov3:
        st.write("")
        st.write("")
        if st.button("Salvar ajuste desta opp", width="stretch", key=f"btn_salvar_{sel}"):
            novo_override = dict(ovr)
            if op_opp != params["opcao_recebimento_default"]:
                novo_override["opcao"] = op_opp
            else:
                novo_override.pop("opcao", None)
            if prazo_opp_new != params["prazo_entrega_cliente"]:
                novo_override["prazo_entrega_cliente"] = prazo_opp_new
            else:
                novo_override.pop("prazo_entrega_cliente", None)
            set_override_opp(params, sel, novo_override)
            save_params(params)
            st.success("Ajuste salvo.")
            st.rerun()


# ============================================================
# ABA 3 — Comparar pedidos (cards + matriz agregada)
# ============================================================
with tab_compara:
    st.markdown("### Filtrar e selecionar pedidos")
    st.caption("Filtros específicos desta aba (não alteram a Tabela & Totais).")

    cf1, cf2, cf3 = st.columns([1.3, 1.3, 1])
    with cf1:
        codigos_cp = ["Todos"] + sorted([c for c in calc_df["codigo"].dropna().unique() if c and c != "—"])
        codigo_cp = st.selectbox("Código do produto", codigos_cp, key="cp_codigo")
    with cf2:
        v_min_cp = float(calc_df["valor"].min())
        v_max_cp = float(calc_df["valor"].max())
        faixa_cp = st.slider("Faixa de valor (R$)",
                             min_value=v_min_cp, max_value=v_max_cp,
                             value=(v_min_cp, v_max_cp),
                             step=1000.0, key="cp_faixa")
    with cf3:
        st.write("")
        st.write("")
        st.caption(f"{len(calc_df)} opp(s) antes · filtrando…")

    df_cp = calc_df.copy()
    if codigo_cp != "Todos":
        df_cp = df_cp[df_cp["codigo"] == codigo_cp]
    df_cp = df_cp[(df_cp["valor"] >= faixa_cp[0]) & (df_cp["valor"] <= faixa_cp[1])]
    df_cp = df_cp.sort_values("valor", ascending=False).reset_index(drop=True)

    st.caption(f"**{len(df_cp)} pedido(s) visíveis após filtros da aba.**")

    # botões globais
    if "sel_multi" not in st.session_state:
        st.session_state.sel_multi = set()

    cbt1, cbt2, _ = st.columns([1, 1, 6])
    with cbt1:
        if st.button("Selecionar visíveis", width="stretch"):
            for n in df_cp["nome"]:
                st.session_state.sel_multi.add(n)
            st.rerun()
    with cbt2:
        if st.button("Limpar seleção", width="stretch"):
            st.session_state.sel_multi = set()
            st.rerun()

    # cards sintéticos (4 colunas)
    num_cols = 4
    for i in range(0, len(df_cp), num_cols):
        cols = st.columns(num_cols)
        for j, c in enumerate(cols):
            if i + j >= len(df_cp):
                break
            row = df_cp.iloc[i + j]
            key_ck = f"ck_cp_{row['nome']}"
            is_sel = row["nome"] in st.session_state.sel_multi
            with c:
                novo = st.checkbox(
                    f"**{row['cliente']}**",
                    value=is_sel, key=key_ck,
                )
                if novo and row["nome"] not in st.session_state.sel_multi:
                    st.session_state.sel_multi.add(row["nome"])
                elif not novo and row["nome"] in st.session_state.sel_multi:
                    st.session_state.sel_multi.discard(row["nome"])

                st.markdown(
                    f"""<div class="opp-card-min">
<div class="opc-linha"><span>Código</span><b>{row['codigo']}</b></div>
<div class="opc-linha"><span>Potência</span><b>{_fmt_mwp(row['potencia_mwp'])}</b></div>
<div class="opc-linha"><span>Valor</span><b>{_fmt_brl(row['valor'], sinal=False)}</b></div>
<div class="opc-linha"><span>Aporte</span><b>{_fmt_brl(row['aporte'], sinal=False)}</b></div>
<div class="opc-linha"><span>Resultado GF2</span>
  <b style="color:{_color(row['resultado_gf2'])}">{_fmt_brl(row['resultado_gf2'])}</b></div>
</div>""",
                    unsafe_allow_html=True,
                )

    st.markdown("---")

    # Fluxo agregado
    selecionados = [n for n in df_cp["nome"] if n in st.session_state.sel_multi]
    if not selecionados:
        st.info("Selecione pedidos nos cards acima para ver o fluxo agregado.")
    else:
        fluxos = []
        for nome in selecionados:
            row_raw = df_f[df_f["nome"] == nome].iloc[0]
            f, *_ = _calc_fluxo_row(row_raw, params)
            fluxos.append(f)

        soma = somar_fluxos(fluxos)

        st.markdown(f"### Fluxo agregado — {len(selecionados)} pedido(s)")

        s1, s2, s3, s4, s5, s6 = st.columns(6)
        s1.metric("Pedidos", _fmt_num(len(selecionados)))
        s2.metric("Valor total", _fmt_brl(soma["valor_total"], sinal=False))
        s3.metric("Margem", _fmt_brl(soma["margem_contribuicao"]),
                  delta=f"{_fmt_num(soma['margem_contribuicao']/soma['valor_total']*100, 1)}% do valor"
                        if soma["valor_total"] else "—")
        s4.metric("Aporte total (escrow)", _fmt_brl(soma["aporte"], sinal=False))
        s5.metric("Juros ao fundo", _fmt_brl(soma["juros_fundo"], sinal=False))
        s6.metric("Resultado GF2", _fmt_brl(soma["resultado_gf2"]),
                  delta=f"{_fmt_num(soma['resultado_gf2']/soma['valor_total']*100, 1)}% do valor"
                        if soma["valor_total"] else "—")

        st.markdown("#### Matriz de fluxo agregado (dia × categoria)")
        st.caption("Soma linha a linha de todos os pedidos selecionados, com os dias alinhados por união.")
        st.markdown(
            _render_matriz(soma["matriz"], soma["fluxo_dia"],
                           soma["acumulado"], soma["acumulado_com_aporte"]),
            unsafe_allow_html=True,
        )


# ============================================================
# ABA 4 — Como funciona
# ============================================================
with tab_ajuda:
    st.markdown("""
### Como funciona a memória (`params.json`)

O dashboard tem **dois níveis** de parâmetros:

**1. Parâmetros globais** — valem para **todos os pedidos** sem override.
  - `taxa_juros_mensal` — taxa do fundo sobre o aporte em escrow
  - `prazo_entrega_cliente` — D+X em que a GF2 entrega
  - `opcao_recebimento_default` — op1 (50/25/25), op2 (30/70) ou op3 (50/50)
  - `categorias_custo[nome]` — % do faturamento e prazo do fornecedor de cada insumo
  - `dias_pagamento[nome]` — dia manual de pagamento (se diferente do automático)

  Editados no **sidebar**. Só persistem no arquivo ao clicar em **💾 Salvar globais**. Sem salvar, valem só para a sessão atual.

**2. Overrides por pedido** — sobrepõem o global **apenas para aquela opp**.
  - Aba **Fluxo por pedido** → botão **Salvar ajuste desta opp**
  - Guardados em `overrides_opp[nome_opp]` no `params.json`
  - Hierarquia: `override da opp` > `global` > `default do código`

Exemplo: se você mudar `prazo_entrega_cliente` no sidebar para 60 dias, **todos os pedidos** usam 60 dias — exceto os que tenham override explícito (ex: Lopes Energy com 90 dias).

---

### Lógica dos parâmetros

Para cada pedido, o dashboard:

1. Lê **categorias de custo** (7 linhas: Aço+Galv, Alumínio, Insumos Produção, Mão de Obra, ADM/Comercial, Frete, Imposto). % somam 90% por default → margem 10%.
2. Lê a **opção de recebimento** do cliente: parcelas em (% e dia corrido).
3. Para cada categoria **não-imposto**, calcula o **dia de pagamento**:
  - Se há valor manual em `dias_pagamento[nome]`, usa esse.
  - Senão, calcula automático: insumo = `entrega_cliente − prazo_fornecedor`; operacional = `entrega_cliente`.
4. **Impostos** são distribuídos proporcionalmente às parcelas recebidas.
5. Monta a **matriz dia × categoria**: entradas positivas (valor da proposta) e negativas (custos).
6. Calcula **fluxo do dia** (soma vertical) e **acumulado** (cumsum).
7. **Aporte / Exposição** = |mínimo do acumulado| (dinheiro que o fundo precisa bancar no pior momento).
8. **Juros ao fundo** = aporte × (taxa_mês/30/100) × dias_operação (linear, conta escrow).
9. Adiciona linha **Quitação fundo (aporte + juros)** no último dia → o acumulado com aporte termina em **Resultado GF2** (margem − juros).

---

### Dia de pagamento — por que (às vezes) não muda o aporte

Quando você muda o dia de pagamento de um insumo, o **aporte só diminui** se o novo dia cair **depois de uma entrada de dinheiro do cliente**.

**Por quê**: o aporte = pior acumulado negativo. Se você antecipar o aço de D+30 pra D+1, o "pior momento" ainda é D+40 (quando todos os insumos já foram pagos e o cliente ainda não pagou a segunda parcela) — então o aporte fica igual.

**Para reduzir o aporte**, mova um pagamento para **depois de D+45** (entrega, 25% do cliente) ou **depois de D+75** (última parcela). Exemplo real com Lopes 50MWp (Op1):

| Cenário (Lopes 50MWp, Op1) | Dia de pagamento | Aporte |
|---|---|---|
| Default (Aço D+1, Alum D+35, Insumos D+40) | padrão | R$ 2.098.687,50 |
| Mover Aço pra D+44 | Aço D+44 | R$ 2.098.687,50 (igual) |
| Mover Alumínio pra D+74 | Alum D+74 | **R$ 1.791.562,50** (−R$ 307k) |
| Mover Aço pra D+74 | Aço D+74 | **~R$ 75k** (drástico) |

Ou seja: o que alivia o caixa é **negociar prazo com fornecedor pra pagar depois do cliente ter pagado você**. O card **Aporte** na aba "Fluxo por pedido" mostra o **dia do pior momento** — se você move um pagamento e o dia do pior momento continua o mesmo, o aporte não muda.

---

### Checklist para salvar alterações

| Ação | Onde | Como persiste |
|---|---|---|
| Mudar taxa do fundo | Sidebar → Taxa | 💾 Salvar globais |
| Mudar % de uma categoria | Sidebar → expander da categoria | 💾 Salvar globais |
| Mudar dia de pagamento de uma categoria | Sidebar → expander → "Dia de pagamento" | 💾 Salvar globais |
| Trocar opção de recebimento dessa opp | Aba Fluxo por pedido → Ajustes | Salvar ajuste desta opp |
| Trocar prazo de entrega dessa opp | Aba Fluxo por pedido → Ajustes | Salvar ajuste desta opp |

Se você **não clicar em Salvar**, as mudanças valem até você fechar o navegador. Quando reabrir, volta ao último estado salvo em `params.json`.
""")
