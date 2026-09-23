from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.portfolio import hypothesis_tests as ht


# --------------------------------------------------------------------------
# factor_changes
# --------------------------------------------------------------------------

def test_factor_changes_rate_kind_is_simple_diff():
    series = pd.Series([0.10, 0.11, 0.105])
    changes = ht.factor_changes(series, "rate")
    np.testing.assert_allclose(changes, [0.01, -0.005])


def test_factor_changes_price_kind_is_log_return():
    series = pd.Series([100.0, 110.0, 99.0])
    changes = ht.factor_changes(series, "price")
    np.testing.assert_allclose(changes, [np.log(110 / 100), np.log(99 / 110)])


def test_factor_changes_price_kind_rejects_nonpositive():
    with pytest.raises(ValueError):
        ht.factor_changes(pd.Series([100.0, -5.0]), "price")


def test_factor_changes_too_short_raises():
    with pytest.raises(ValueError):
        ht.factor_changes(pd.Series([100.0]), "price")


def test_factor_changes_invalid_kind_raises():
    with pytest.raises(ValueError):
        ht.factor_changes(pd.Series([1.0, 2.0]), "nao_existe")


# --------------------------------------------------------------------------
# skewness / excess_kurtosis / qq_correlation
# --------------------------------------------------------------------------

def test_skewness_symmetric_data_is_near_zero():
    x = np.array([-2, -1, 0, 1, 2], dtype=float)
    assert abs(ht.skewness(x)) < 1e-9


def test_skewness_right_skewed_data_is_positive():
    x = np.array([0, 0, 0, 0, 0, 0, 0, 0, 0, 100.0])
    assert ht.skewness(x) > 1.0


def test_skewness_constant_series_edge_case():
    assert ht.skewness(np.array([5.0, 5.0, 5.0])) == 0.0


def test_skewness_empty_raises():
    with pytest.raises(ValueError):
        ht.skewness(np.array([]))


def test_excess_kurtosis_constant_series_edge_case():
    assert ht.excess_kurtosis(np.array([1.0, 1.0, 1.0])) == 0.0


def test_excess_kurtosis_empty_raises():
    with pytest.raises(ValueError):
        ht.excess_kurtosis(np.array([]))


def test_excess_kurtosis_heavy_tailed_is_positive():
    x = np.array([0, 0, 0, 0, 0, 0, 0, 0, -50.0, 50.0])
    assert ht.excess_kurtosis(x) > 0


def test_qq_correlation_normal_like_sample_is_close_to_one():
    rng = np.random.default_rng(123)
    x = rng.standard_normal(2000)
    assert ht.qq_correlation(x) > 0.99


def test_qq_correlation_too_few_points_raises():
    with pytest.raises(ValueError):
        ht.qq_correlation(np.array([1.0, 2.0]))


def test_qq_correlation_constant_series_edge_case():
    assert ht.qq_correlation(np.array([3.0, 3.0, 3.0, 3.0])) == 0.0


# --------------------------------------------------------------------------
# normality_test
# --------------------------------------------------------------------------

def test_normality_test_accepts_symmetric_gaussian_like_sample():
    rng = np.random.default_rng(7)
    x = rng.standard_normal(2000)
    result = ht.normality_test(x)
    assert result["rejects_normality"] is False


def test_normality_test_rejects_clearly_skewed_sample():
    x = np.array([0, 0, 0, 0, 0, 0, 0, 0, 0, 100.0])
    result = ht.normality_test(x)
    assert result["rejects_normality"] is True


# --------------------------------------------------------------------------
# acf / autocorrelation_test
# --------------------------------------------------------------------------

def test_acf_lag_zero_or_negative_raises():
    with pytest.raises(ValueError):
        ht.acf(np.array([1.0, 2.0, 3.0]), 0)


def test_acf_lag_too_large_raises():
    with pytest.raises(ValueError):
        ht.acf(np.array([1.0, 2.0, 3.0]), 3)


def test_acf_constant_series_edge_case():
    assert ht.acf(np.array([2.0, 2.0, 2.0, 2.0]), 1) == 0.0


def test_acf_linear_trend_has_strong_lag1_autocorrelation():
    x = np.arange(1, 21, dtype=float)
    assert ht.acf(x, 1) > 0.8


def test_autocorrelation_test_too_short_series_raises():
    with pytest.raises(ValueError):
        ht.autocorrelation_test(np.arange(5, dtype=float), lags=(1, 5, 10))


def test_autocorrelation_test_trend_rejects_iid():
    x = np.arange(1, 51, dtype=float)
    result = ht.autocorrelation_test(x, lags=(1, 5))
    assert result["rejects_iid"] is True
    assert result["significant"][1] is True


def test_autocorrelation_test_white_noise_like_sample_may_not_reject():
    rng = np.random.default_rng(99)
    x = rng.standard_normal(5000)
    result = ht.autocorrelation_test(x, lags=(1,))
    assert abs(result["acf"][1]) < result["significance_bound"] * 3  # sanidade, não estatisticamente exato


# --------------------------------------------------------------------------
# stationarity_test
# --------------------------------------------------------------------------

def test_stationarity_test_n_windows_too_small_raises():
    with pytest.raises(ValueError):
        ht.stationarity_test(np.arange(20, dtype=float), n_windows=1)


def test_stationarity_test_series_too_short_raises():
    with pytest.raises(ValueError):
        ht.stationarity_test(np.arange(5, dtype=float), n_windows=4)


def test_stationarity_test_constant_series_does_not_reject():
    x = np.full(40, 5.0)
    result = ht.stationarity_test(x, n_windows=4)
    assert result["rejects_stationarity"] is False


def test_stationarity_test_regime_shift_rejects():
    x = np.concatenate([np.zeros(20), np.full(20, 100.0)])
    result = ht.stationarity_test(x, n_windows=4)
    assert result["rejects_stationarity"] is True
