from __future__ import annotations

import math

import pytest

from src.pipeline.contracts import ActionResult, RunContext
from src.tests_extended import liquidity_horizon_scaling as lhs


def _ctx(elasticidade: list[dict]) -> RunContext:
    stability = ActionResult(status="success", output={"elasticidade": elasticidade})
    return RunContext(run_id="r", memory=None, llm_client=None, inputs={}, results={"07_stability_tests": stability})


def test_missing_stability_results_is_skipped():
    ctx = RunContext(run_id="r", memory=None, llm_client=None, inputs={}, results={})
    result = lhs.run(ctx)
    assert result.status == "skipped"


def test_no_rows_at_reference_shock_is_skipped():
    rows = [{"metrica": "VaR", "cenario": "isolado", "fator": "usdbrl", "choque": 0.05, "delta_metrica": 10.0}]
    ctx = _ctx(rows)
    result = lhs.run(ctx)
    assert result.status == "skipped"


def test_scaling_matches_hand_computed_values():
    rows = [
        {"metrica": "VaR", "cenario": "isolado", "fator": "usdbrl", "choque": 0.01, "delta_metrica": 10.0},  # LH=10
        {"metrica": "VaR", "cenario": "isolado", "fator": "cpr", "choque": 0.01, "delta_metrica": 10.0},  # LH=120
    ]
    ctx = _ctx(rows)
    result = lhs.run(ctx)

    assert result.status == "success"
    assert result.output["total_horizonte_uniforme_10d"] == pytest.approx(math.sqrt(200))
    assert result.output["total_horizonte_por_categoria"] == pytest.approx(math.sqrt(1300))
    assert result.output["razao_liquidez_vs_uniforme"] == pytest.approx(math.sqrt(1300 / 200))

    by_factor = {r["fator"]: r for r in result.output["por_fator"]}
    assert by_factor["usdbrl"]["horizonte_liquidez_dias"] == 10
    assert by_factor["cpr"]["horizonte_liquidez_dias"] == 120
    assert by_factor["cpr"]["delta_ajustado_liquidez"] == pytest.approx(10.0 * math.sqrt(12))


def test_unknown_factor_uses_default_horizon():
    rows = [{"metrica": "VaR", "cenario": "isolado", "fator": "fator_novo_desconhecido", "choque": 0.01, "delta_metrica": 5.0}]
    ctx = _ctx(rows)
    result = lhs.run(ctx)

    assert result.output["por_fator"][0]["horizonte_liquidez_dias"] == lhs.DEFAULT_HORIZON_DAYS


def test_zero_baseline_gives_none_ratio_without_crashing():
    rows = [{"metrica": "VaR", "cenario": "isolado", "fator": "usdbrl", "choque": 0.01, "delta_metrica": 0.0}]
    ctx = _ctx(rows)
    result = lhs.run(ctx)

    assert result.status == "success"
    assert result.output["razao_liquidez_vs_uniforme"] is None
