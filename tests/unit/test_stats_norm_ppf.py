from __future__ import annotations

import math

import pytest

from src.portfolio import _stats


def test_norm_ppf_median_is_zero():
    assert math.isclose(_stats.norm_ppf(0.5), 0.0, abs_tol=1e-9)


def test_norm_ppf_out_of_range_raises():
    with pytest.raises(ValueError):
        _stats.norm_ppf(0.0)
    with pytest.raises(ValueError):
        _stats.norm_ppf(1.0)
    with pytest.raises(ValueError):
        _stats.norm_ppf(-0.1)


def test_norm_ppf_is_inverse_of_norm_cdf():
    for p in (0.01, 0.1, 0.25, 0.5, 0.75, 0.9, 0.99):
        x = _stats.norm_ppf(p)
        assert math.isclose(_stats.norm_cdf(x), p, abs_tol=1e-6)


def test_norm_ppf_fallback_matches_scipy_within_tolerance(monkeypatch):
    reference = {p: _stats.norm_ppf(p) for p in (0.001, 0.025, 0.1, 0.5, 0.9, 0.975, 0.999)}
    monkeypatch.setattr(_stats, "_HAS_SCIPY", False)
    for p, expected in reference.items():
        assert math.isclose(_stats.norm_ppf(p), expected, abs_tol=1e-6)


def test_norm_ppf_symmetry():
    assert math.isclose(_stats.norm_ppf(0.25), -_stats.norm_ppf(0.75), abs_tol=1e-9)
