# Fomento GF2 — Dashboard de Fomento à Produção (Risco Sacado)

Dashboard Streamlit para analisar pedidos da GF2 Soluções Integradas sob o modelo de **fomento à produção em conta escrow**. Calcula, pedido a pedido, o aporte necessário, os juros pagos ao fundo e o resultado líquido da GF2.

## Features

- **Tabela & Totais** — visão agregada com cards por categoria de custo
- **Fluxo por pedido** — matriz dia × categoria em dias corridos, com quitação do fundo no final
- **Comparar pedidos** — seleção múltipla + matriz de fluxo somado
- **Como funciona** — documentação inline da lógica e memória

Fonte: xlsx embarcado (lista das 31 opps +R$ 40k) + Salesforce em tempo real (código do produto, quantidade de módulos, conta, fase).

## Stack

- Python 3.12 + Streamlit
- simple-salesforce (OAuth refresh_token)
- Plotly · Pandas · openpyxl

## Rodar local

```bash
cp .env.example .env   # preencha as credenciais
pip install -r requirements.txt
streamlit run app.py
```

Porta default: 8503. Acesso por senha via `APP_PASSWORD` no `.env`.

## Deploy (Streamlit Community Cloud)

1. Conecte este repo em https://share.streamlit.io
2. Em **Settings → Secrets**, cole o conteúdo de `.streamlit/secrets.toml.example` preenchido
3. Main file: `app.py`
4. Python 3.12

## Estrutura

```
fomento-gf2/
├── app.py                  # UI (4 abas) + auth
├── config.py               # Categorias de custo, opções de recebimento, cores GF2
├── data.py                 # Load xlsx + enriquecimento SF
├── fomento.py              # Cálculo de resumo (custos, margem)
├── timeline.py             # Matriz de fluxo, soma de fluxos, quitação do fundo
├── parser.py               # Parser do nome da opp
├── params_store.py         # Persistência JSON (global + overrides por opp)
├── salesforce_client.py    # OAuth + queries SOQL
├── data/opps_gf2.xlsx      # Lista de 31 opps (snapshot)
└── requirements.txt
```

## Modelo de cálculo

7 categorias de custo (90% do faturamento → 10% margem):
- Aço+Galvanização 56% (paga D+1) · Alumínio 3% · Insumos Produção 7%
- Mão de Obra 6% · ADM/Comercial 3% · Frete 6% · Imposto 9%

3 opções de recebimento do cliente:
- **Op 1**: 50% D+1 · 25% D+45 · 25% D+75
- **Op 2**: 30% D+1 · 70% D+55
- **Op 3**: 50% D+1 · 50% D+45

Fundo banca o aporte (exposição máxima negativa) em conta escrow e cobra juros lineares (default 1,5% ao mês) pelo período total da operação.
