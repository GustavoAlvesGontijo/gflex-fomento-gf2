"""Calculadora do fomento à produção (risco sacado) — GF2.

Modelo:
- 7 categorias de custo em % do faturamento (Aço+Galv, Alumínio, Insumos,
  Mão de Obra, ADM, Frete, Imposto) — editáveis por opp.
- 3 opções de recebimento do cliente (parcelas em % e dia corrido).
- Insumos: fornecedor paga à vista na data da compra e entrega X dias depois.
- Operacionais (mão de obra, ADM, frete): contabilizados no dia da entrega.
- Imposto: proporcional a cada parcela recebida.
"""
from dataclasses import dataclass


@dataclass
class ResumoFomento:
    valor: float
    custos_pct: dict           # {categoria: pct}
    custos_rs: dict            # {categoria: R$}
    custo_total: float
    custo_total_pct: float
    margem_bruta: float
    margem_bruta_pct: float


def calcular_resumo(valor: float, categorias: dict[str, dict]) -> ResumoFomento:
    """Calcula custos e margem bruta de uma opp.

    Args:
        valor: faturamento do pedido (R$).
        categorias: dict com chave=nome da categoria e value={"pct": float, ...}.
    """
    valor = max(0.0, float(valor or 0))

    custos_pct = {c: float(v.get("pct", 0)) for c, v in categorias.items()}
    custos_rs = {c: valor * pct / 100.0 for c, pct in custos_pct.items()}

    custo_total = sum(custos_rs.values())
    custo_total_pct = (custo_total / valor * 100.0) if valor else 0.0

    margem_bruta = valor - custo_total
    margem_bruta_pct = (margem_bruta / valor * 100.0) if valor else 0.0

    return ResumoFomento(
        valor=valor,
        custos_pct=custos_pct,
        custos_rs=custos_rs,
        custo_total=custo_total,
        custo_total_pct=custo_total_pct,
        margem_bruta=margem_bruta,
        margem_bruta_pct=margem_bruta_pct,
    )
