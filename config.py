"""Config central do Dashboard de Fomento GF2."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Salesforce
SF_CLIENT_ID = os.getenv("SF_CLIENT_ID", "")
SF_CLIENT_SECRET = os.getenv("SF_CLIENT_SECRET", "")
SF_REFRESH_TOKEN = os.getenv("SF_REFRESH_TOKEN", "")
SF_INSTANCE_URL = os.getenv("SF_INSTANCE_URL", "https://gflex-empresas.my.salesforce.com")
SF_DOMAIN = os.getenv("SF_DOMAIN", "login")

# Dados — xlsx embarcado no repo (cloud-safe), mas pode ser sobrescrito via .env
PROJECT_ROOT = Path(__file__).parent
_XLSX_EMBUTIDO = PROJECT_ROOT / "data" / "opps_gf2.xlsx"
OPPORTUNITIES_XLSX = Path(os.getenv("OPPORTUNITIES_XLSX", _XLSX_EMBUTIDO))
PARAMS_FILE = PROJECT_ROOT / "params.json"

# Empresa
EMPRESA_SF = "GF2 Soluções Integradas"

# Cores (manual da marca GFlex — GF2)
COR_PRIMARIA = "#004A9D"
COR_SECUNDARIA = "#ffffff"
COR_FUNDO = "#ffffff"
COR_POSITIVO = "#1F8A2E"
COR_NEGATIVO = "#C62828"
COR_NEUTRO = "#6B7280"

# Cache
CACHE_TTL_SECONDS = 300

# --- Modelo do fomento (inputs do Gustavo) ---

# 7 categorias de custo, % sobre faturamento e prazo de entrega do fornecedor
# (dias entre pagamento e chegada do material). Fornecedores pagam à vista.
#
# `dia_pagamento_default` (opcional): fixa o dia corrido de pagamento. Quando
# presente, sobrepõe o cálculo automático (entrega_cliente − prazo_fornecedor).
# Aço+Galvanização é pago em D+1 por padrão.
CATEGORIAS_CUSTO_DEFAULT: dict[str, dict] = {
    "Aço+Galvanização":  {"pct": 56.0, "prazo_entrega_fornecedor": 15, "tipo": "insumo",
                          "dia_pagamento_default": 1},
    "Alumínio":          {"pct": 3.0,  "prazo_entrega_fornecedor": 10, "tipo": "insumo"},
    "Insumos Produção":  {"pct": 7.0,  "prazo_entrega_fornecedor": 5,  "tipo": "insumo"},
    "Mão de Obra":       {"pct": 6.0,  "prazo_entrega_fornecedor": 0,  "tipo": "operacional"},
    "ADM/Comercial":     {"pct": 3.0,  "prazo_entrega_fornecedor": 0,  "tipo": "operacional"},
    "Frete":             {"pct": 6.0,  "prazo_entrega_fornecedor": 0,  "tipo": "operacional"},
    "Imposto":           {"pct": 9.0,  "prazo_entrega_fornecedor": 0,  "tipo": "imposto"},
}
# Total custos default: 90% → Margem: 10%

# 3 opções de recebimento do cliente — cada parcela é (% do valor, dia corrido)
OPCOES_RECEBIMENTO: dict[str, dict] = {
    "op1": {
        "label": "50/25/25 — 50% entrada · 25% entrega · 25% +30d",
        "parcelas": [(50.0, 1), (25.0, 45), (25.0, 75)],
    },
    "op2": {
        "label": "30/70 — 30% entrada · 70% +10d após entrega",
        "parcelas": [(30.0, 1), (70.0, 55)],
    },
    "op3": {
        "label": "50/50 — 50% entrada · 50% na entrega (menos aceita)",
        "parcelas": [(50.0, 1), (50.0, 45)],
    },
}

OPCAO_RECEBIMENTO_DEFAULT = "op1"
PRAZO_ENTREGA_CLIENTE_DEFAULT = 45  # dias corridos até a entrega

# Taxa de juros do fomento (usada para calcular TIR exigida vs oferecida)
DEFAULT_TAXA_JUROS_MENSAL = 1.5  # % ao mês sobre o valor aportado (conta escrow)

# Módulos fotovoltaicos: potência unitária em W (padrão de mercado atual)
POTENCIA_POR_MODULO_W = 600
