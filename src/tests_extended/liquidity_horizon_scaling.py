"""Teste extensível: escalonamento por horizonte de liquidez, estilo FRTB
(CLAUDE.md §Action 09).

FRTB (BCBS d457/d352) atribui a cada categoria de fator de risco um horizonte
de liquidez (LH) em dias, e escalona choques por √(LH/10) em vez de assumir
um único horizonte uniforme de 10 dias para todos os fatores. Este módulo
reaproveita os resultados já calculados pela Action 07 e recalcula a mesma
soma (raiz da soma dos quadrados, aproximação padrão de agregação sob
independência) sob dois cenários: horizonte uniforme de 10 dias vs. horizonte
por categoria — para mostrar o quanto a escolha de horizonte de liquidez
muda a métrica agregada.

IMPORTANTE: o mapeamento fator→LH abaixo é uma CONVENÇÃO PRÓPRIA deste
repositório (documentada e plausível, análoga às categorias de liquidez do
FRTB), não uma tabela oficial do BCBS transcrita de memória — nunca deve ser
citada como "os LH do FRTB" sem essa ressalva (CLAUDE.md §6 regra 2: nunca
inventar número de norma).
"""

from __future__ import annotations

import math

from src.pipeline.contracts import ActionResult, RunContext

TEST_ID = "liquidity_horizon_scaling"
REFERENCE_SHOCK = 0.01
BASELINE_HORIZON_DAYS = 10

# Convenção própria (não uma tabela oficial do BCBS) — categorias mais
# líquidas (câmbio/ações principais) têm LH menor; comportamentais (NMD,
# CPR) são tratados como os menos líquidos por dependerem de modelagem, não
# de mercado observável.
LIQUIDITY_HORIZON_DAYS: dict[str, int] = {
    "di_pre": 20, "ipca_real": 20, "pre_nominal": 20, "ust": 20, "sofr": 20, "fed_funds": 20,
    "usdbrl": 10, "ibov": 10, "spx": 10, "soja": 20, "brent": 20, "wti": 20,
    "vol_ibov": 40, "vol_spx": 40, "vol_usdbrl": 40, "vol_juros": 40,
    "spread_debentures": 60, "spread_bonds_corp": 60,
    "nmd_decay_rate": 120, "cpr": 120,
}
DEFAULT_HORIZON_DAYS = 20


def run(ctx: RunContext) -> ActionResult:
    stability = ctx.results.get("07_stability_tests")
    if stability is None or not stability.output.get("elasticidade"):
        return ActionResult(
            status="skipped",
            output={"por_fator": []},
            notes=["Sem resultados de estabilidade (Action 07) — escalonamento de liquidez não calculável nesta run."],
        )

    isolated = [
        r for r in stability.output["elasticidade"]
        if r.get("cenario") == "isolado" and r.get("choque") == REFERENCE_SHOCK
    ]
    if not isolated:
        return ActionResult(
            status="skipped",
            output={"por_fator": []},
            notes=[f"Nenhum resultado isolado no choque de referência ({REFERENCE_SHOCK:g})."],
        )

    baseline_scale = math.sqrt(BASELINE_HORIZON_DAYS / BASELINE_HORIZON_DAYS)  # = 1.0, explícito por clareza
    rows = []
    baseline_sum_sq = 0.0
    liquidity_sum_sq = 0.0
    for r in isolated:
        horizon = LIQUIDITY_HORIZON_DAYS.get(r["fator"], DEFAULT_HORIZON_DAYS)
        liquidity_scale = math.sqrt(horizon / BASELINE_HORIZON_DAYS)
        baseline_component = r["delta_metrica"] * baseline_scale
        liquidity_component = r["delta_metrica"] * liquidity_scale
        baseline_sum_sq += baseline_component**2
        liquidity_sum_sq += liquidity_component**2
        rows.append({
            "metrica": r["metrica"], "fator": r["fator"], "horizonte_liquidez_dias": horizon,
            "delta_base": r["delta_metrica"], "delta_ajustado_liquidez": liquidity_component,
        })

    total_baseline = math.sqrt(baseline_sum_sq)
    total_liquidez = math.sqrt(liquidity_sum_sq)
    razao = (total_liquidez / total_baseline) if total_baseline > 0 else None

    notes = [
        f"Agregado sob horizonte uniforme de {BASELINE_HORIZON_DAYS}d: {total_baseline:.4f}; "
        f"sob horizonte por categoria (convenção própria, não tabela oficial do BCBS): {total_liquidez:.4f} "
        f"(razão: {razao:.2f}x)." if razao is not None else "Agregado base é zero — razão indefinida.",
    ]

    return ActionResult(
        status="success",
        output={
            "por_fator": rows,
            "total_horizonte_uniforme_10d": total_baseline,
            "total_horizonte_por_categoria": total_liquidez,
            "razao_liquidez_vs_uniforme": razao,
            "liquidity_horizon_days_convention": LIQUIDITY_HORIZON_DAYS,
        },
        notes=notes,
    )
