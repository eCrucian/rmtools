"""Normal CDF/PDF com fallback numpy puro (CLAUDE.md §2.2) — usado pelos modelos
de precificação (Black-Scholes/Black-76) e pelo gerador de fatores de risco."""

from __future__ import annotations

import math

try:
    from scipy.stats import norm as _scipy_norm

    _HAS_SCIPY = True
except ImportError:  # pragma: no cover - exercitado quando scipy não está instalado
    _HAS_SCIPY = False


def norm_cdf(x: float) -> float:
    if _HAS_SCIPY:
        return float(_scipy_norm.cdf(x))
    return _abramowitz_stegun_cdf(x)


def norm_pdf(x: float) -> float:
    if _HAS_SCIPY:
        return float(_scipy_norm.pdf(x))
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def norm_ppf(p: float) -> float:
    """Inversa da normal padrão (quantil) — usada no QQ-plot numérico de
    normalidade (CLAUDE.md §Action 04)."""
    if not (0.0 < p < 1.0):
        raise ValueError(f"p deve estar em (0, 1), recebido {p!r}")
    if _HAS_SCIPY:
        return float(_scipy_norm.ppf(p))
    return _acklam_ppf(p)


def _acklam_ppf(p: float) -> float:
    """Aproximação racional de Peter Acklam (domínio público), erro relativo
    máximo ~1.15e-9 — precisão de sobra para thresholds de teste de hipótese."""
    a = [-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02,
         1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00]
    b = [-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02,
         6.680131188771972e01, -1.328068155288572e01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00,
         -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00,
         3.754408661907416e00]

    p_low = 0.02425
    p_high = 1.0 - p_low

    if p < p_low:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )
    if p <= p_high:
        q = p - 0.5
        r = q * q
        return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (
            (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)
        )
    q = math.sqrt(-2.0 * math.log(1.0 - p))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
        (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
    )


def _abramowitz_stegun_cdf(x: float) -> float:
    """Aproximação de Abramowitz & Stegun 26.2.17 (erro máx. ~7.5e-8)."""
    sign = 1.0 if x >= 0 else -1.0
    x = abs(x) / math.sqrt(2.0)

    a1, a2, a3, a4, a5 = 0.254829592, -0.284496736, 1.421413741, -1.453152027, 1.061405429
    p = 0.3275911

    t = 1.0 / (1.0 + p * x)
    y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * math.exp(-x * x)
    return 0.5 * (1.0 + sign * y)
