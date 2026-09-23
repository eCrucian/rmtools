from __future__ import annotations

import pytest

from src.pipeline.actions import _stability_engine as se


# --------------------------------------------------------------------------
# shock_market
# --------------------------------------------------------------------------

def test_shock_market_isolated_only_changes_target_factor():
    market = {"di_pre": 0.10, "usdbrl": 5.0}
    shocked = se.shock_market(market, "di_pre", 0.05)
    assert shocked["di_pre"] == pytest.approx(0.105)
    assert shocked["usdbrl"] == 5.0


def test_shock_market_joint_changes_all_factors():
    market = {"di_pre": 0.10, "usdbrl": 5.0}
    shocked = se.shock_market(market, None, 0.10)
    assert shocked["di_pre"] == pytest.approx(0.11)
    assert shocked["usdbrl"] == pytest.approx(5.5)


def test_shock_market_does_not_mutate_original():
    market = {"di_pre": 0.10}
    se.shock_market(market, "di_pre", 0.05)
    assert market["di_pre"] == 0.10


# --------------------------------------------------------------------------
# classify_elasticity
# --------------------------------------------------------------------------

def test_classify_elasticity_perfectly_linear_is_ok():
    elasticidade, flag, ok = se.classify_elasticity(valor_base=100.0, valor_choque=105.0, shock_pct=0.05)
    assert elasticidade == 1.0
    assert flag == "ok"
    assert ok is True


def test_classify_elasticity_explosion_is_flagged():
    # valor sobe 60% para um choque de 1% -> elasticidade = 60, acima do teto de 50
    elasticidade, flag, ok = se.classify_elasticity(valor_base=100.0, valor_choque=160.0, shock_pct=0.01)
    assert elasticidade == 60.0
    assert flag == "explosao"
    assert ok is False


def test_classify_elasticity_insensitivity_is_flagged_at_10pct_shock():
    elasticidade, flag, ok = se.classify_elasticity(valor_base=100.0, valor_choque=100.00005, shock_pct=0.10)
    assert flag == "insensivel"
    assert ok is False


def test_classify_elasticity_small_shock_insensitivity_not_flagged():
    # a regra de insensibilidade só se aplica a choques >= 10% (§Action 07)
    elasticidade, flag, ok = se.classify_elasticity(valor_base=100.0, valor_choque=100.00005, shock_pct=0.01)
    assert flag != "insensivel"


def test_classify_elasticity_without_reference_skips_linearity_check():
    # sem reference_elasticity (ex.: primeiro/menor choque testado para um
    # fator), não há base de comparação — mesmo uma elasticidade "estranha"
    # não é classificada como não-linear nesse ponto.
    elasticidade, flag, ok = se.classify_elasticity(valor_base=100.0, valor_choque=110.0, shock_pct=0.05)
    assert elasticidade == 2.0
    assert flag == "ok"
    assert ok is True


def test_classify_elasticity_deviates_from_reference_is_flagged_nonlinear():
    # elasticidade = 2.0, desvio de 100% em relação à referência (1.0) —
    # acima do limite default de 20%.
    elasticidade, flag, ok = se.classify_elasticity(
        valor_base=100.0, valor_choque=110.0, shock_pct=0.05, reference_elasticity=1.0
    )
    assert elasticidade == 2.0
    assert flag == "nao_linear"
    assert ok is False


def test_classify_elasticity_close_to_reference_is_ok():
    # elasticidade = 1.05, desvio de 5% em relação à referência (1.0) — dentro do limite.
    elasticidade, flag, ok = se.classify_elasticity(
        valor_base=100.0, valor_choque=105.25, shock_pct=0.05, reference_elasticity=1.0
    )
    assert flag == "ok"
    assert ok is True


def test_classify_elasticity_reference_near_zero_skips_linearity_check():
    # referência ~0 (fator praticamente irrelevante) tornaria o desvio
    # relativo indefinido/explosivo por construção — a checagem é pulada.
    elasticidade, flag, ok = se.classify_elasticity(
        valor_base=100.0, valor_choque=100.5, shock_pct=0.01, reference_elasticity=1e-12
    )
    assert flag == "ok"


def test_classify_elasticity_zero_base_with_zero_delta_is_ok():
    elasticidade, flag, ok = se.classify_elasticity(valor_base=0.0, valor_choque=0.0, shock_pct=0.05)
    assert elasticidade is None
    assert flag == "ok"
    assert ok is True


def test_classify_elasticity_zero_base_with_nonzero_delta_is_indeterminate():
    elasticidade, flag, ok = se.classify_elasticity(valor_base=0.0, valor_choque=5.0, shock_pct=0.05)
    assert elasticidade is None
    assert flag == "indeterminado_base_zero"
    assert ok is True


def test_classify_elasticity_zero_shock_is_ok():
    elasticidade, flag, ok = se.classify_elasticity(valor_base=100.0, valor_choque=100.0, shock_pct=0.0)
    assert elasticidade is None
    assert flag == "ok"
    assert ok is True


def test_classify_elasticity_custom_bounds_are_respected():
    bounds = {"fator_explosao_max": 5.0, "insensibilidade_min_pct": 0.001, "desvio_linearidade_max": 0.20}
    elasticidade, flag, ok = se.classify_elasticity(valor_base=100.0, valor_choque=110.0, shock_pct=0.01, bounds=bounds)
    assert elasticidade == 10.0
    assert flag == "explosao"
    assert ok is False


# --------------------------------------------------------------------------
# portfolio_value / run_isolated_and_joint_tests / run_correlation_break_test
# (com price_portfolio monkeypatchado — mantém o teste focado na orquestração
# do motor, não na precificação real, já coberta por test_pricing_models.py)
# --------------------------------------------------------------------------

def _fake_price_portfolio(positions, market):
    return {1: market["di_pre"] * 1_000_000.0}


def _fake_build_portfolio_input(positions, market):
    return {"value": market["di_pre"] * 1_000_000.0, "positions": []}


def _fake_compute(portfolio, risk_factors, params):
    return {"valor": portfolio["value"] * params.get("multiplicador", 2.0)}


def test_portfolio_value_sums_price_portfolio(monkeypatch):
    monkeypatch.setattr(se, "price_portfolio", _fake_price_portfolio)
    value = se.portfolio_value(["qualquer"], {"di_pre": 0.10})
    assert value == 100_000.0


def test_run_isolated_and_joint_tests_produces_expected_result_count(monkeypatch):
    monkeypatch.setattr(se, "build_portfolio_input", _fake_build_portfolio_input)
    results = se.run_isolated_and_joint_tests(
        metrica="VaR",
        compute=_fake_compute,
        params={},
        positions=["qualquer"],
        base_market={"di_pre": 0.10},
        base_returns=[],
        choques_pct=(0.01, 0.05),
        factor_names=("di_pre",),
    )
    # 1 fator x 2 choques (isolado) + 2 choques (conjunto) = 4
    assert len(results) == 4
    cenarios = {r.cenario for r in results}
    assert cenarios == {"isolado", "conjunto"}


def test_run_isolated_and_joint_tests_elasticity_is_linear_for_linear_setup(monkeypatch):
    monkeypatch.setattr(se, "build_portfolio_input", _fake_build_portfolio_input)
    results = se.run_isolated_and_joint_tests(
        metrica="VaR",
        compute=_fake_compute,
        params={},
        positions=["qualquer"],
        base_market={"di_pre": 0.10},
        base_returns=[],
        choques_pct=(0.05,),
        factor_names=("di_pre",),
    )
    isolado = next(r for r in results if r.cenario == "isolado")
    assert isolado.elasticidade == pytest.approx(1.0)
    assert isolado.flag == "ok"
    assert isolado.dentro_do_limite is True


def test_run_correlation_break_test_returns_informative_flag(monkeypatch):
    monkeypatch.setattr(se, "build_portfolio_input", _fake_build_portfolio_input)
    result = se.run_correlation_break_test(
        metrica="VaR",
        compute=_fake_compute,
        params={},
        positions=["qualquer"],
        base_market={"di_pre": 0.10},
        base_returns=[],
        stressed_market={"di_pre": 0.20},
    )
    assert result.cenario == "quebra_correlacao"
    assert result.choque is None
    assert result.flag == "informativo"
    assert result.dentro_do_limite is True
    assert result.valor_choque == 400_000.0  # 0.20 * 1_000_000 * multiplicador(2.0)
