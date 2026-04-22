"""Persistência local dos parâmetros do dashboard (params.json).

Novo modelo:
- categorias_custo: dict[nome, {pct, prazo_entrega_fornecedor, tipo}]
- opcao_recebimento_default: "op1"/"op2"/"op3"
- prazo_entrega_cliente: dias corridos
- taxa_juros_mensal: % ao mês (para referência)
- overrides_opp: dict[opp_nome, {categorias, opcao, prazo_entrega}]
"""
import json
from pathlib import Path
import copy
from config import (
    PARAMS_FILE,
    CATEGORIAS_CUSTO_DEFAULT,
    OPCAO_RECEBIMENTO_DEFAULT,
    PRAZO_ENTREGA_CLIENTE_DEFAULT,
    DEFAULT_TAXA_JUROS_MENSAL,
)


def default_params() -> dict:
    return {
        "categorias_custo": copy.deepcopy(CATEGORIAS_CUSTO_DEFAULT),
        "opcao_recebimento_default": OPCAO_RECEBIMENTO_DEFAULT,
        "prazo_entrega_cliente": PRAZO_ENTREGA_CLIENTE_DEFAULT,
        "taxa_juros_mensal": DEFAULT_TAXA_JUROS_MENSAL,
        "dias_pagamento": {},     # {nome_categoria: dia_corrido_D+N}
        "overrides_opp": {},      # {nome_opp: {opcao, prazo_entrega_cliente, dias_pagamento}}
    }


def load_params() -> dict:
    p = Path(PARAMS_FILE)
    if not p.exists():
        return default_params()
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return default_params()
    base = default_params()
    # Merge raso: mantém keys esperadas, sobrescreve com o que veio do arquivo
    for k in base.keys():
        if k in data:
            base[k] = data[k]
    # Garante que todas as categorias default existem, mesmo se o arquivo for antigo
    for nome, conf in CATEGORIAS_CUSTO_DEFAULT.items():
        if nome not in base["categorias_custo"]:
            base["categorias_custo"][nome] = copy.deepcopy(conf)
        else:
            for k, v in conf.items():
                base["categorias_custo"][nome].setdefault(k, v)
    return base


def save_params(params: dict) -> None:
    p = Path(PARAMS_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(params, f, indent=2, ensure_ascii=False)


def get_override_opp(params: dict, opp_nome: str) -> dict:
    return params.get("overrides_opp", {}).get(opp_nome, {})


def set_override_opp(params: dict, opp_nome: str, override: dict) -> None:
    overrides = params.setdefault("overrides_opp", {})
    if not override:
        overrides.pop(opp_nome, None)
    else:
        overrides[opp_nome] = override


def categorias_para_opp(params: dict, opp_nome: str) -> dict:
    """Retorna as categorias aplicadas a essa opp (com overrides se houver)."""
    base = copy.deepcopy(params["categorias_custo"])
    ovr = get_override_opp(params, opp_nome).get("categorias", {})
    for nome, conf in ovr.items():
        if nome in base:
            base[nome].update(conf)
        else:
            base[nome] = conf
    return base
