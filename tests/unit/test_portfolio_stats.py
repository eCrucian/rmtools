from __future__ import annotations

import math

from src.portfolio import _stats


def test_norm_cdf_at_zero_is_one_half():
    assert math.isclose(_stats.norm_cdf(0.0), 0.5, abs_tol=1e-9)


def test_norm_cdf_extremes_saturate():
    assert _stats.norm_cdf(10.0) > 0.999999
    assert _stats.norm_cdf(-10.0) < 0.000001


def test_norm_cdf_symmetry():
    assert math.isclose(_stats.norm_cdf(1.5) + _stats.norm_cdf(-1.5), 1.0, abs_tol=1e-9)


def test_norm_pdf_at_zero():
    assert math.isclose(_stats.norm_pdf(0.0), 1.0 / math.sqrt(2 * math.pi), abs_tol=1e-9)


def test_fallback_matches_scipy_within_tolerance(monkeypatch):
    reference = {x: _stats.norm_cdf(x) for x in (-2.5, -1.0, 0.0, 0.5, 2.0, 3.0)}
    monkeypatch.setattr(_stats, "_HAS_SCIPY", False)
    for x, expected in reference.items():
        assert math.isclose(_stats.norm_cdf(x), expected, abs_tol=1e-6)


def test_fallback_pdf_used_when_no_scipy(monkeypatch):
    monkeypatch.setattr(_stats, "_HAS_SCIPY", False)
    assert math.isclose(_stats.norm_pdf(0.0), 1.0 / math.sqrt(2 * math.pi), abs_tol=1e-9)
