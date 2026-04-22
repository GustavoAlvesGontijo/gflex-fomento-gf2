"""Fluxo de caixa em dias corridos e métricas do fundo.

Matriz dia × categoria ala Excel PEDIDOS_GF2 - FLUXO:
- Linhas: VALOR PROPOSTA + 7 categorias de custo + Quitação fundo (no último dia)
- Colunas: dias corridos (D+0, dias de pagamento, D+entrega, dias de recebimento final)
- Linhas-resumo: fluxo do dia, acumulado, acumulado com aporte
- Métricas: aporte, juros ao fundo, resultado GF2

Regras padrão:
- Insumos pagos em D+(entrega − prazo_fornecedor) para chegar a tempo da entrega
- Operacionais no dia da entrega
- Impostos proporcionais a cada parcela recebida
- Fundo quita no último dia da operação (aporte + juros)

Opcional: `dias_pagamento_override` permite definir o dia de pagamento de cada
categoria individualmente (ex.: {"Aço+Galvanização": 1, "Alumínio": 1}).
"""
from __future__ import annotations
from dataclasses import dataclass
import pandas as pd


LINHA_QUITACAO = "Quitação fundo (aporte + juros)"


@dataclass
class ResultadoFluxo:
    valor: float
    prazo_entrega_cliente: int
    dias: list[int]                        # eixo x: dias corridos
    matriz: pd.DataFrame                   # linhas=categoria+quitação, cols=dias
    fluxo_dia: pd.Series                   # soma vertical (inclui quitação)
    acumulado: pd.Series                   # cumsum sem aporte (inclui quitação)
    aporte: float                          # capital bancado em escrow
    acumulado_com_aporte: pd.Series        # inclui aporte + quitação; termina em resultado_gf2
    saldo_final: float                     # = resultado_gf2
    margem_contribuicao: float             # valor − todos os custos
    margem_pct: float
    dias_operacao: int
    taxa_mes: float
    juros_fundo: float                     # aporte × taxa_dia × dias_operacao
    resultado_gf2: float                   # margem − juros
    resultado_gf2_pct: float


def _dia_pagamento_default(conf: dict, prazo_entrega_cliente: int) -> int:
    """Dia de pagamento padrão de uma categoria.

    Respeita `dia_pagamento_default` se presente na configuração da categoria
    (ex.: Aço+Galvanização → D+1). Caso contrário, calcula automaticamente.
    """
    if "dia_pagamento_default" in conf:
        return max(0, int(conf["dia_pagamento_default"]))
    if conf.get("tipo") == "insumo":
        return max(0, prazo_entrega_cliente - int(conf.get("prazo_entrega_fornecedor", 0)))
    if conf.get("tipo") == "operacional":
        return prazo_entrega_cliente
    if conf.get("tipo") == "imposto":
        return -1
    return prazo_entrega_cliente


def gerar_fluxo(
    valor: float,
    categorias: dict[str, dict],
    opcao_recebimento: dict,
    prazo_entrega_cliente: int,
    taxa_mes: float = 1.5,
    dias_pagamento_override: dict[str, int] | None = None,
) -> ResultadoFluxo:
    """Monta a matriz de fluxo com quitação do fundo no último dia."""
    valor = max(0.0, float(valor or 0))
    overrides = dias_pagamento_override or {}

    # Descobrir todos os dias envolvidos
    dias_set = {0, int(prazo_entrega_cliente)}
    for pct, dia in opcao_recebimento["parcelas"]:
        dias_set.add(int(dia))
    for nome, conf in categorias.items():
        if conf.get("tipo") == "imposto":
            continue
        dia_pagto = int(overrides.get(nome, _dia_pagamento_default(conf, prazo_entrega_cliente)))
        dias_set.add(max(0, dia_pagto))
    dias = sorted(dias_set)
    dia_final = dias[-1]

    linhas: dict[str, dict[int, float]] = {}

    # 1) Valor da proposta (entradas do cliente)
    linhas["VALOR DA PROPOSTA"] = {d: 0.0 for d in dias}
    parcelas_total_pct = sum(pct for pct, _ in opcao_recebimento["parcelas"]) or 1
    for pct, dia in opcao_recebimento["parcelas"]:
        linhas["VALOR DA PROPOSTA"][int(dia)] += valor * pct / 100.0

    # 2) Impostos: proporcionais a cada parcela recebida
    imposto_pct = float(categorias.get("Imposto", {}).get("pct", 0))
    imposto_total = valor * imposto_pct / 100.0
    if imposto_total:
        linhas["Imposto"] = {d: 0.0 for d in dias}
        for pct, dia in opcao_recebimento["parcelas"]:
            linhas["Imposto"][int(dia)] -= imposto_total * (pct / parcelas_total_pct)

    # 3) Insumos e operacionais (não-imposto)
    for nome, conf in categorias.items():
        if conf.get("tipo") == "imposto":
            continue
        pct = float(conf.get("pct", 0))
        if pct <= 0:
            continue
        dia_pagto = max(0, int(overrides.get(nome, _dia_pagamento_default(conf, prazo_entrega_cliente))))
        linhas.setdefault(nome, {d: 0.0 for d in dias})
        linhas[nome][dia_pagto] -= valor * pct / 100.0

    # Monta matriz preliminar (sem quitação) para calcular aporte/juros
    matriz_pre = pd.DataFrame(linhas).T
    matriz_pre = matriz_pre[dias]
    fluxo_dia_pre = matriz_pre.sum(axis=0)
    acumulado_pre = fluxo_dia_pre.cumsum()

    minimo = acumulado_pre.min()
    aporte = float(abs(minimo)) if minimo < 0 else 0.0
    dias_operacao = max(1, (dia_final - dias[0]))
    taxa_dia = max(0.0, float(taxa_mes)) / 30.0 / 100.0
    juros_fundo = aporte * taxa_dia * dias_operacao

    # Adiciona linha de quitação ao fundo no último dia
    linhas[LINHA_QUITACAO] = {d: 0.0 for d in dias}
    linhas[LINHA_QUITACAO][dia_final] -= (aporte + juros_fundo)

    # Matriz final — renomeia colunas pra D+X
    matriz = pd.DataFrame(linhas).T
    matriz = matriz[dias]
    matriz.columns = [f"D+{d}" for d in dias]

    fluxo_dia = matriz.sum(axis=0)
    acumulado = fluxo_dia.cumsum()
    acumulado_com_aporte = acumulado + aporte

    custo_total = sum(valor * float(c.get("pct", 0)) / 100.0 for c in categorias.values())
    margem_contribuicao = valor - custo_total
    margem_pct = (margem_contribuicao / valor * 100.0) if valor else 0.0
    resultado_gf2 = margem_contribuicao - juros_fundo
    resultado_gf2_pct = (resultado_gf2 / valor * 100.0) if valor else 0.0
    saldo_final = float(acumulado_com_aporte.iloc[-1])

    return ResultadoFluxo(
        valor=valor,
        prazo_entrega_cliente=prazo_entrega_cliente,
        dias=dias,
        matriz=matriz,
        fluxo_dia=fluxo_dia,
        acumulado=acumulado,
        aporte=aporte,
        acumulado_com_aporte=acumulado_com_aporte,
        saldo_final=saldo_final,
        margem_contribuicao=margem_contribuicao,
        margem_pct=margem_pct,
        dias_operacao=dias_operacao,
        taxa_mes=float(taxa_mes),
        juros_fundo=juros_fundo,
        resultado_gf2=resultado_gf2,
        resultado_gf2_pct=resultado_gf2_pct,
    )


def somar_fluxos(resultados: list[ResultadoFluxo]) -> dict:
    """Soma várias ResultadoFluxo em um fluxo agregado.

    Retorna uma matriz (categoria × dia) agregada, no mesmo formato da matriz
    individual, acompanhada das linhas-resumo (fluxo_dia, acumulado, com aporte).
    """
    vazio = {
        "dias": [], "matriz": pd.DataFrame(),
        "fluxo_dia": pd.Series(dtype=float),
        "acumulado": pd.Series(dtype=float),
        "acumulado_com_aporte": pd.Series(dtype=float),
        "aporte": 0.0, "juros_fundo": 0.0,
        "margem_contribuicao": 0.0, "resultado_gf2": 0.0,
        "valor_total": 0.0, "dias_operacao": 0,
    }
    if not resultados:
        return vazio

    # União de dias
    todos_dias: set[int] = set()
    categorias_todas: set[str] = set()
    for r in resultados:
        todos_dias.update(r.dias)
        categorias_todas.update(r.matriz.index.tolist())
    dias = sorted(todos_dias)
    cols = [f"D+{d}" for d in dias]

    # Ordenação das categorias: mantém ordem "natural" (VALOR, custos, Quitação)
    ordem_prioridade = [
        "VALOR DA PROPOSTA", "Imposto",
        "Aço+Galvanização", "Alumínio", "Insumos Produção",
        "Mão de Obra", "ADM/Comercial", "Frete",
        LINHA_QUITACAO,
    ]
    cats_ordenadas = [c for c in ordem_prioridade if c in categorias_todas]
    for c in sorted(categorias_todas):
        if c not in cats_ordenadas:
            cats_ordenadas.append(c)

    # Monta matriz agregada: zera tudo e soma cada resultado realinhado
    matriz = pd.DataFrame(0.0, index=cats_ordenadas, columns=cols)
    for r in resultados:
        for cat in r.matriz.index:
            for col in r.matriz.columns:
                if col in cols:
                    matriz.at[cat, col] += float(r.matriz.at[cat, col])

    fluxo_dia = matriz.sum(axis=0)
    acumulado = fluxo_dia.cumsum()
    aporte = sum(r.aporte for r in resultados)
    juros = sum(r.juros_fundo for r in resultados)
    margem = sum(r.margem_contribuicao for r in resultados)
    resultado = sum(r.resultado_gf2 for r in resultados)
    valor_total = sum(r.valor for r in resultados)
    acumulado_com_aporte = acumulado + aporte
    dias_operacao = (dias[-1] - dias[0]) if len(dias) > 1 else 0

    return {
        "dias": dias,
        "matriz": matriz,
        "fluxo_dia": fluxo_dia,
        "acumulado": acumulado,
        "acumulado_com_aporte": acumulado_com_aporte,
        "aporte": aporte,
        "juros_fundo": juros,
        "margem_contribuicao": margem,
        "resultado_gf2": resultado,
        "valor_total": valor_total,
        "dias_operacao": dias_operacao,
    }
