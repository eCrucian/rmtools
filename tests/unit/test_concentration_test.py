from __future__ import annotations

import pytest

from src.pipeline.contracts import ActionResult, RunContext
from src.tests_extended import concentration_test as ct


def _ctx(elasticidade: list[dict]) -> RunContext:
    stability = ActionResult(status="success", output={"elasticidade": elasticidade})
    return RunContext(run_id="r", memory=None, llm_client=None, inputs={}, results={"07_stability_tests": stability})


def test_missing_stability_results_is_skipped():
    ctx = RunContext(run_id="r", memory=None, llm_client=None, inputs={}, results={})
    result = ct.run(ctx)
    assert result.status == "skipped"


def test_empty_elasticidade_is_skipped():
    ctx = _ctx([])
    result = ct.run(ctx)
    assert result.status == "skipped"


def test_no_rows_at_reference_shock_is_skipped():
    rows = [{"metrica": "VaR", "cenario": "isolado", "fator": "di_pre", "choque": 0.05, "delta_metrica": 10.0}]
    ctx = _ctx(rows)
    result = ct.run(ctx)
    assert result.status == "skipped"


def test_concentration_shares_computed_correctly():
    rows = [
        {"metrica": "VaR", "cenario": "isolado", "fator": "A", "choque": 0.01, "delta_metrica": 10.0},
        {"metrica": "VaR", "cenario": "isolado", "fator": "B", "choque": 0.01, "delta_metrica": 5.0},
        {"metrica": "VaR", "cenario": "isolado", "fator": "C", "choque": 0.01, "delta_metrica": -1.0},
        {"metrica": "VaR", "cenario": "conjunto", "fator": "TODOS", "choque": 0.01, "delta_metrica": 999.0},  # ignorado
    ]
    ctx = _ctx(rows)
    result = ct.run(ctx)

    assert result.status == "success"
    by_factor = {c["fator"]: c["share_concentracao"] for c in result.output["concentracao"]}
    assert by_factor["A"] == pytest.approx(10 / 16)
    assert by_factor["B"] == pytest.approx(5 / 16)
    assert by_factor["C"] == pytest.approx(1 / 16)

    assert [c["fator"] for c in result.output["fatores_concentrados"]] == ["A"]
    assert result.output["concentracao"][0]["fator"] == "A"  # ordenado por concentração decrescente


def test_zero_total_delta_gives_zero_shares_without_crashing():
    rows = [
        {"metrica": "VaR", "cenario": "isolado", "fator": "A", "choque": 0.01, "delta_metrica": 0.0},
        {"metrica": "VaR", "cenario": "isolado", "fator": "B", "choque": 0.01, "delta_metrica": 0.0},
    ]
    ctx = _ctx(rows)
    result = ct.run(ctx)

    assert result.status == "success"
    assert all(c["share_concentracao"] == 0.0 for c in result.output["concentracao"])
    assert result.output["fatores_concentrados"] == []
