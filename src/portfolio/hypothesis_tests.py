"""Testes quantitativos de hipótese em numpy puro (CLAUDE.md §Action 04):
normalidade (assimetria/curtose, QQ numérico), autocorrelação/i.i.d. (ACF), e
estacionariedade aproximada (médias/variâncias em subjanelas). Roda contra os
históricos sintéticos congelados da carteira hipotética (§5), lidos via
`data_access.py` — nunca contra dado gerado em tempo de execução.
"""

from __future__ import annotations

import math
from typing import Literal

import numpy as np
import pandas as pd

from ._stats import norm_ppf

FactorKind = Literal["rate", "price"]


def factor_changes(series: pd.Series, kind: FactorKind) -> np.ndarray:
    """Variação diária de um fator: log-retorno para preços (`kind="price"` —
    spots/commodities, sempre positivos), diferença simples para taxas
    (`kind="rate"` — curvas/spreads/comportamentais, podem ser ~0 ou negativas)."""
    values = series.to_numpy(dtype=float)
    if len(values) < 2:
        raise ValueError("série precisa de pelo menos 2 observações para calcular variações")
    if kind == "price":
        if np.any(values <= 0):
            raise ValueError("kind='price' exige série estritamente positiva para log-retorno")
        return np.diff(np.log(values))
    if kind == "rate":
        return np.diff(values)
    raise ValueError(f"kind inválido: {kind!r} (esperado 'rate' ou 'price')")


def skewness(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    if len(x) == 0:
        raise ValueError("assimetria requer ao menos uma observação")
    s = x.std(ddof=0)
    if s == 0:
        return 0.0
    return float(np.mean(((x - x.mean()) / s) ** 3))


def excess_kurtosis(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    if len(x) == 0:
        raise ValueError("curtose requer ao menos uma observação")
    s = x.std(ddof=0)
    if s == 0:
        return 0.0
    return float(np.mean(((x - x.mean()) / s) ** 4) - 3.0)


def qq_correlation(x: np.ndarray) -> float:
    """Correlação entre quantis empíricos e quantis teóricos N(0,1) — 1.0 =
    ajuste perfeito à normal (proxy numérico de um QQ-plot, §Action 04)."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n < 3:
        raise ValueError("QQ-plot numérico requer ao menos 3 observações")
    x_sorted = np.sort(x)
    probs = (np.arange(1, n + 1) - 0.5) / n
    theoretical = np.array([norm_ppf(p) for p in probs])
    if x_sorted.std(ddof=0) == 0:
        return 0.0  # série constante: não há como correlacionar com a teórica
    return float(np.corrcoef(x_sorted, theoretical)[0, 1])


def normality_test(
    x: np.ndarray, *, skew_threshold: float = 0.5, kurt_threshold: float = 1.0, qq_threshold: float = 0.98
) -> dict:
    """Convenção de limiares documentada aqui (não há norma única de mercado
    para isso): |assimetria| > 0.5 OU |curtose em excesso| > 1.0 OU
    correlação QQ < 0.98 rejeita normalidade."""
    skew = skewness(x)
    kurt = excess_kurtosis(x)
    qq = qq_correlation(x)
    rejects = abs(skew) > skew_threshold or abs(kurt) > kurt_threshold or qq < qq_threshold
    return {
        "skewness": skew,
        "excess_kurtosis": kurt,
        "qq_correlation": qq,
        "thresholds": {"skew": skew_threshold, "kurtosis": kurt_threshold, "qq_correlation": qq_threshold},
        "rejects_normality": rejects,
    }


def acf(x: np.ndarray, lag: int) -> float:
    x = np.asarray(x, dtype=float)
    n = len(x)
    if lag < 1:
        raise ValueError("lag deve ser >= 1")
    if lag >= n:
        raise ValueError(f"lag ({lag}) deve ser menor que o tamanho da série ({n})")
    x0 = x - x.mean()
    denom = np.sum(x0**2)
    if denom == 0:
        return 0.0
    numerator = np.sum(x0[: n - lag] * x0[lag:])
    return float(numerator / denom)


def autocorrelation_test(x: np.ndarray, lags: tuple[int, ...] = (1, 5, 10)) -> dict:
    """Limite aproximado de significância a 95% para ruído branco: ±1.96/√n
    (convenção padrão de séries temporais)."""
    n = len(np.asarray(x))
    if n < max(lags) + 1:
        raise ValueError(f"série (n={n}) curta demais para os lags pedidos ({lags})")
    bound = 1.96 / math.sqrt(n)
    values = {lag: acf(x, lag) for lag in lags}
    significant = {lag: abs(v) > bound for lag, v in values.items()}
    return {
        "acf": values,
        "significance_bound": bound,
        "significant": significant,
        "rejects_iid": any(significant.values()),
    }


def stationarity_test(x: np.ndarray, *, n_windows: int = 4, cv_threshold: float = 0.5) -> dict:
    """Divide a série em `n_windows` subjanelas e compara média/variância
    entre elas via coeficiente de variação — aproximação simples de
    estacionariedade quando `statsmodels` não está disponível (§2.2/§Action 04)."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n_windows < 2:
        raise ValueError("n_windows deve ser >= 2")
    if n < n_windows * 2:
        raise ValueError(f"série (n={n}) curta demais para {n_windows} subjanelas")

    window_size = n // n_windows
    means: list[float] = []
    variances: list[float] = []
    for i in range(n_windows):
        start = i * window_size
        end = n if i == n_windows - 1 else start + window_size
        window = x[start:end]
        means.append(float(window.mean()))
        variances.append(float(window.var(ddof=0)))

    mean_of_means = np.mean(means)
    mean_cv = float(np.std(means) / abs(mean_of_means)) if mean_of_means != 0 else float(np.std(means))
    mean_of_vars = np.mean(variances)
    var_cv = float(np.std(variances) / mean_of_vars) if mean_of_vars != 0 else float(np.std(variances))

    rejects = mean_cv > cv_threshold or var_cv > cv_threshold
    return {
        "window_means": means,
        "window_variances": variances,
        "mean_cv": mean_cv,
        "var_cv": var_cv,
        "threshold": cv_threshold,
        "rejects_stationarity": rejects,
    }
