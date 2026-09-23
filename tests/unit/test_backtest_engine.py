from __future__ import annotations

import math

import numpy as np
import pytest

from src.pipeline.actions import _backtest_engine as be


# --------------------------------------------------------------------------
# chi2 CDF / critical value (forma fechada via normal, sem scipy)
# --------------------------------------------------------------------------

def test_chi2_cdf_df1_negative_is_zero():
    assert be.chi2_cdf_df1(-1.0) == 0.0


def test_chi2_cdf_df2_negative_is_zero():
    assert be.chi2_cdf_df2(-1.0) == 0.0


def test_chi2_critical_df1_matches_well_known_value():
    # valor tabelado clássico: χ²(1) a 95% ≈ 3.841
    assert be.chi2_critical_df1(0.05) == pytest.approx(3.841458820694124, rel=1e-6)


def test_chi2_critical_df2_matches_well_known_value():
    # valor tabelado clássico: χ²(2) a 95% ≈ 5.991
    assert be.chi2_critical_df2(0.05) == pytest.approx(5.991464547107981, rel=1e-6)


def test_chi2_cdf_df1_at_its_own_critical_value_is_95pct():
    x = be.chi2_critical_df1(0.05)
    assert be.chi2_cdf_df1(x) == pytest.approx(0.95, rel=1e-6)


def test_chi2_cdf_df2_at_its_own_critical_value_is_95pct():
    x = be.chi2_critical_df2(0.05)
    assert be.chi2_cdf_df2(x) == pytest.approx(0.95, rel=1e-6)


# --------------------------------------------------------------------------
# _binom_loglik
# --------------------------------------------------------------------------

def test_binom_loglik_zero_total_is_zero():
    assert be._binom_loglik(0, 0, 0.5) == 0.0


def test_binom_loglik_prob_zero_no_successes_is_zero():
    assert be._binom_loglik(10, 0, 0.0) == 0.0


def test_binom_loglik_prob_zero_with_successes_is_negative_infinity():
    assert be._binom_loglik(10, 1, 0.0) == float("-inf")


def test_binom_loglik_prob_one_all_successes_is_zero():
    assert be._binom_loglik(10, 10, 1.0) == 0.0


def test_binom_loglik_prob_one_with_failures_is_negative_infinity():
    assert be._binom_loglik(10, 5, 1.0) == float("-inf")


def test_binom_loglik_normal_case_matches_manual_formula():
    expected = 7 * math.log(0.9) + 3 * math.log(0.1)
    assert be._binom_loglik(10, 3, 0.1) == pytest.approx(expected)


# --------------------------------------------------------------------------
# kupiec_pof_test
# --------------------------------------------------------------------------

def test_kupiec_invalid_n_obs_raises():
    with pytest.raises(ValueError):
        be.kupiec_pof_test(0, 0, 0.99)


def test_kupiec_invalid_n_exceptions_raises():
    with pytest.raises(ValueError):
        be.kupiec_pof_test(100, 101, 0.99)
    with pytest.raises(ValueError):
        be.kupiec_pof_test(100, -1, 0.99)


def test_kupiec_invalid_confidence_raises():
    with pytest.raises(ValueError):
        be.kupiec_pof_test(100, 1, 1.0)
    with pytest.raises(ValueError):
        be.kupiec_pof_test(100, 1, 0.0)


def test_kupiec_observed_rate_matches_expected_does_not_reject():
    # n=1000, confiança 99% -> esperado 10 exceções; observado exatamente 10
    result = be.kupiec_pof_test(n_obs=1000, n_exceptions=10, confidence=0.99)
    assert result["lr_stat"] == pytest.approx(0.0, abs=1e-9)
    assert result["rejeita_h0"] is False


def test_kupiec_far_too_many_exceptions_rejects():
    # 100 exceções em 1000 observações para um VaR de 99% (esperado 10) é
    # uma violação grosseira do nível de confiança.
    result = be.kupiec_pof_test(n_obs=1000, n_exceptions=100, confidence=0.99)
    assert result["rejeita_h0"] is True
    assert result["lr_stat"] > result["critical_value"]


def test_kupiec_zero_exceptions_is_valid_and_does_not_crash():
    result = be.kupiec_pof_test(n_obs=100, n_exceptions=0, confidence=0.99)
    assert result["n_exceptions"] == 0
    assert math.isfinite(result["lr_stat"])


def test_kupiec_all_exceptions_is_valid_and_rejects():
    result = be.kupiec_pof_test(n_obs=50, n_exceptions=50, confidence=0.99)
    assert result["rejeita_h0"] is True


# --------------------------------------------------------------------------
# christoffersen_independence_test
# --------------------------------------------------------------------------

def test_christoffersen_too_few_observations_raises():
    with pytest.raises(ValueError):
        be.christoffersen_independence_test([True])


def test_christoffersen_no_exceptions_does_not_reject():
    result = be.christoffersen_independence_test([False] * 20)
    assert result["lr_stat"] == pytest.approx(0.0, abs=1e-9)
    assert result["rejeita_h0"] is False


def test_christoffersen_clustered_exceptions_rejects():
    # exceções perfeitamente agrupadas (violam independência: uma exceção
    # sempre segue outra) devem ter LR muito maior que exceções espalhadas.
    clustered = [False] * 40 + [True] * 10 + [False] * 40
    scattered = [i % 9 == 0 for i in range(90)]  # ~mesma taxa, mas espalhada
    clustered_result = be.christoffersen_independence_test(clustered)
    scattered_result = be.christoffersen_independence_test(scattered)
    assert clustered_result["lr_stat"] > scattered_result["lr_stat"]
    assert clustered_result["rejeita_h0"] is True


def test_christoffersen_alternating_never_two_in_a_row():
    exceedances = [i % 2 == 0 for i in range(20)]
    result = be.christoffersen_independence_test(exceedances)
    assert result["n11"] == 0


# --------------------------------------------------------------------------
# christoffersen_conditional_coverage
# --------------------------------------------------------------------------

def test_conditional_coverage_sums_the_two_statistics():
    kupiec = be.kupiec_pof_test(1000, 10, 0.99)
    christoffersen = be.christoffersen_independence_test([False] * 990 + [True] * 10)
    cc = be.christoffersen_conditional_coverage(kupiec, christoffersen)
    assert cc["lr_stat"] == pytest.approx(kupiec["lr_stat"] + christoffersen["lr_stat"])
    assert cc["critical_value"] == pytest.approx(be.chi2_critical_df2(0.05))


# --------------------------------------------------------------------------
# basel_traffic_light
# --------------------------------------------------------------------------

@pytest.mark.parametrize("n,expected", [(0, "verde"), (4, "verde"), (5, "amarela"), (9, "amarela"), (10, "vermelha"), (25, "vermelha")])
def test_basel_traffic_light_boundaries(n, expected):
    assert be.basel_traffic_light(n) == expected


def test_basel_traffic_light_negative_raises():
    with pytest.raises(ValueError):
        be.basel_traffic_light(-1)


# --------------------------------------------------------------------------
# compute_rolling_var_1day
# --------------------------------------------------------------------------

def test_compute_rolling_var_1day_too_short_raises():
    with pytest.raises(ValueError):
        be.compute_rolling_var_1day(lambda p, r, prm: {"valor": 1.0}, {}, np.array([1.0, 2.0, 3.0]), rolling_window=5)


def test_compute_rolling_var_1day_produces_expected_indices_and_calls():
    calls = []

    def fake_compute(portfolio, risk_factors, params):
        calls.append((portfolio["value"], len(risk_factors["returns"])))
        return {"valor": 42.0}

    value_series = np.array([100.0, 101.0, 102.0, 103.0, 104.0, 105.0])
    indices, var_1day = be.compute_rolling_var_1day(fake_compute, {}, value_series, rolling_window=3)

    assert list(indices) == [3, 4, 5]
    assert list(var_1day) == [42.0, 42.0, 42.0]
    assert calls == [(103.0, 3), (104.0, 3), (105.0, 3)]


def test_compute_rolling_var_1day_uses_portfolio_inputs_when_provided():
    """Regressão: métricas de exposição por posição (ex.: SA-CCR) leem
    `portfolio['positions']`, não só `portfolio['value']` — sem passar
    `portfolio_inputs`, essas métricas quebram com `KeyError('positions')`
    ao rodar o backtest (bug real encontrado rodando a fixture doc_boa)."""
    calls = []

    def saccr_like_compute(portfolio, risk_factors, params):
        calls.append(portfolio["positions"])
        return {"valor": sum(p["notional"] for p in portfolio["positions"])}

    value_series = np.array([100.0, 101.0, 102.0, 103.0, 104.0, 105.0])
    portfolio_inputs = [
        {"value": float(v), "positions": [{"notional": float(v) * 10}]} for v in value_series
    ]

    indices, var_1day = be.compute_rolling_var_1day(
        saccr_like_compute, {}, value_series, rolling_window=3, portfolio_inputs=portfolio_inputs
    )

    assert list(indices) == [3, 4, 5]
    assert var_1day.tolist() == [1030.0, 1040.0, 1050.0]
    assert calls == [[{"notional": 1030.0}], [{"notional": 1040.0}], [{"notional": 1050.0}]]


# --------------------------------------------------------------------------
# backtest_for_holding_period
# --------------------------------------------------------------------------

def test_backtest_holding_period_less_than_one_raises():
    with pytest.raises(ValueError):
        be.backtest_for_holding_period(np.array([1.0]), np.array([0]), np.array([1.0]), 0, 0.99)


def test_backtest_no_usable_observations_raises():
    value_series = np.array([100.0] * 5)
    indices = np.array([3, 4])
    var_1day = np.array([1.0, 1.0])
    with pytest.raises(ValueError):
        be.backtest_for_holding_period(value_series, indices, var_1day, holding_period=10, confidence=0.99)


def test_backtest_constant_series_has_no_exceptions():
    value_series = np.array([100.0] * 10)
    indices = np.array([3, 4, 5, 6, 7, 8, 9])
    var_1day = np.array([1.0] * 7)

    result = be.backtest_for_holding_period(value_series, indices, var_1day, holding_period=1, confidence=0.99)

    assert result["n_obs"] == 6  # índice 9 descartado (precisa de 9+1=10, fora do array)
    assert result["n_exceptions"] == 0
    assert result["semaforo"] == "verde"
    assert result["semaforo_e_canonico"] is True
    assert result["christoffersen"] is not None
    assert result["cobertura_condicional"] is not None


def test_backtest_every_day_a_huge_loss_flags_all_exceptions():
    # monotonicamente decrescente -> toda transição idx->idx+1 é uma perda real
    value_series = np.array([100.0 - 10.0 * i for i in range(10)])
    indices = np.array([3, 4, 5, 6, 7, 8])
    var_1day = np.array([1.0] * 6)  # VaR minúsculo -> toda queda de 10 estoura o limite

    result = be.backtest_for_holding_period(value_series, indices, var_1day, holding_period=1, confidence=0.99)

    assert result["n_exceptions"] == result["n_obs"] == 6
    assert result["semaforo"] == "amarela"  # 6 exceções em 6 obs. -> zona amarela (5-9)
    assert result["kupiec"]["rejeita_h0"] is True


def test_backtest_holding_period_scales_var_by_sqrt_h():
    # n=14 (índices válidos 0..13): com holding_period=4, o índice 10 exigiria
    # o ponto 10+4=14 (fora do array) e é descartado — só h=1 o mantém.
    value_series = np.array([100.0] * 14)
    indices = np.array([3, 4, 5, 6, 7, 8, 9, 10])
    var_1day = np.array([1.0] * 8)

    result_h1 = be.backtest_for_holding_period(value_series, indices, var_1day, holding_period=1, confidence=0.99)
    result_h4 = be.backtest_for_holding_period(value_series, indices, var_1day, holding_period=4, confidence=0.99)

    # série constante -> P&L sempre 0 -> nenhuma exceção em nenhum holding period,
    # mas o número de observações utilizáveis cai conforme h cresce.
    assert result_h4["n_obs"] < result_h1["n_obs"]
    assert result_h4["holding_period"] == 4
    assert result_h4["semaforo_e_canonico"] is False
