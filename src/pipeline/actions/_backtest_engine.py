"""Motor de backtest (CLAUDE.md §Action 08): Kupiec (POF), Christoffersen
(independência) e semáforo de Basileia, por holding period.

χ² sem scipy (§2.2): para os graus de liberdade relevantes (1 e 2), a CDF do
χ² tem forma fechada EXATA em função da normal padrão — não precisa de tabela
aproximada nem de scipy:
  - χ²(df=1) é o quadrado de uma N(0,1): CDF(x) = 2·Φ(√x) - 1
  - χ²(df=2) é uma exponencial de média 2: CDF(x) = 1 - exp(-x/2)
`_stats.norm_cdf`/`norm_ppf` já existem com fallback próprio (§2.2), então
esses dois casos cobrem exatamente Kupiec (df=1), Christoffersen (df=1) e o
teste conjunto (df=1+1=2) sem nenhuma dependência externa.
"""

from __future__ import annotations

import math
from typing import Callable

import numpy as np

from src.portfolio._stats import norm_cdf, norm_ppf

DEFAULT_ROLLING_WINDOW = 250
MIN_HISTORY_DAYS = 250
DEFAULT_CONFIDENCE = 0.99
SIGNIFICANCE_ALPHA = 0.05

BASEL_GREEN_MAX = 4
BASEL_YELLOW_MAX = 9


def chi2_cdf_df1(x: float) -> float:
    if x < 0:
        return 0.0
    return 2.0 * norm_cdf(math.sqrt(x)) - 1.0


def chi2_cdf_df2(x: float) -> float:
    if x < 0:
        return 0.0
    return 1.0 - math.exp(-x / 2.0)


def chi2_critical_df1(alpha: float = SIGNIFICANCE_ALPHA) -> float:
    return norm_ppf(1.0 - alpha / 2.0) ** 2


def chi2_critical_df2(alpha: float = SIGNIFICANCE_ALPHA) -> float:
    return -2.0 * math.log(alpha)


def _binom_loglik(n_total: int, n_success: int, prob: float) -> float:
    """log-verossimilhança binomial, com os casos de canto de `prob` em
    {0,1} e `n_total=0` resolvidos por convenção (0·log(0) := 0)."""
    if n_total == 0:
        return 0.0
    if prob <= 0.0:
        return 0.0 if n_success == 0 else float("-inf")
    if prob >= 1.0:
        return 0.0 if n_success == n_total else float("-inf")
    n_fail = n_total - n_success
    return n_fail * math.log(1.0 - prob) + n_success * math.log(prob)


def kupiec_pof_test(n_obs: int, n_exceptions: int, confidence: float, alpha: float = SIGNIFICANCE_ALPHA) -> dict:
    """Proportion-of-failures test (Kupiec 1995). `confidence` é o nível de
    confiança do VaR (ex.: 0.99); a taxa de exceção esperada é `1-confidence`."""
    if n_obs <= 0:
        raise ValueError("n_obs deve ser > 0")
    if n_exceptions < 0 or n_exceptions > n_obs:
        raise ValueError("n_exceptions deve estar entre 0 e n_obs")
    if not (0.0 < confidence < 1.0):
        raise ValueError("confidence deve estar em (0, 1)")

    p_expected = 1.0 - confidence
    pi_hat = n_exceptions / n_obs

    log_lik_null = _binom_loglik(n_obs, n_exceptions, p_expected)
    log_lik_alt = _binom_loglik(n_obs, n_exceptions, pi_hat)
    lr_stat = max(0.0, -2.0 * (log_lik_null - log_lik_alt))

    critical = chi2_critical_df1(alpha)
    p_value = 1.0 - chi2_cdf_df1(lr_stat)
    return {
        "n_obs": n_obs,
        "n_exceptions": n_exceptions,
        "taxa_observada": pi_hat,
        "taxa_esperada": p_expected,
        "lr_stat": lr_stat,
        "critical_value": critical,
        "p_value": p_value,
        "rejeita_h0": lr_stat > critical,
    }


def christoffersen_independence_test(exceedances: list[bool], alpha: float = SIGNIFICANCE_ALPHA) -> dict:
    """Testa se as exceções (indicador 0/1 por dia) são independentes ao
    longo do tempo — clusterização de violações indicaria falha do modelo em
    reagir a mudanças de regime de volatilidade."""
    n = len(exceedances)
    if n < 2:
        raise ValueError("christoffersen_independence_test requer ao menos 2 observações")

    n00 = n01 = n10 = n11 = 0
    for prev, curr in zip(exceedances[:-1], exceedances[1:]):
        if not prev and not curr:
            n00 += 1
        elif not prev and curr:
            n01 += 1
        elif prev and not curr:
            n10 += 1
        else:
            n11 += 1

    n0_total = n00 + n01
    n1_total = n10 + n11
    n_trans_total = n0_total + n1_total

    pi01 = n01 / n0_total if n0_total > 0 else 0.0
    pi11 = n11 / n1_total if n1_total > 0 else 0.0
    pi_pooled = (n01 + n11) / n_trans_total if n_trans_total > 0 else 0.0

    log_lik_restricted = _binom_loglik(n0_total, n01, pi_pooled) + _binom_loglik(n1_total, n11, pi_pooled)
    log_lik_unrestricted = _binom_loglik(n0_total, n01, pi01) + _binom_loglik(n1_total, n11, pi11)
    lr_stat = max(0.0, -2.0 * (log_lik_restricted - log_lik_unrestricted))

    critical = chi2_critical_df1(alpha)
    p_value = 1.0 - chi2_cdf_df1(lr_stat)
    return {
        "n00": n00, "n01": n01, "n10": n10, "n11": n11,
        "pi01": pi01, "pi11": pi11,
        "lr_stat": lr_stat,
        "critical_value": critical,
        "p_value": p_value,
        "rejeita_h0": lr_stat > critical,
    }


def christoffersen_conditional_coverage(kupiec_result: dict, christoffersen_result: dict, alpha: float = SIGNIFICANCE_ALPHA) -> dict:
    """Teste conjunto (cobertura condicional, df=2): combina Kupiec (nível
    correto de exceções) e Christoffersen (independência) numa única
    estatística — LR_cc = LR_pof + LR_ind."""
    lr_stat = kupiec_result["lr_stat"] + christoffersen_result["lr_stat"]
    critical = chi2_critical_df2(alpha)
    p_value = 1.0 - chi2_cdf_df2(lr_stat)
    return {"lr_stat": lr_stat, "critical_value": critical, "p_value": p_value, "rejeita_h0": lr_stat > critical}


def basel_traffic_light(n_exceptions: int) -> str:
    """Semáforo de Basileia (janela de 250 dias, uso canônico a 1 dia) —
    cortes regulatórios padrão: 0-4 verde, 5-9 amarela, 10+ vermelha."""
    if n_exceptions < 0:
        raise ValueError("n_exceptions não pode ser negativo")
    if n_exceptions <= BASEL_GREEN_MAX:
        return "verde"
    if n_exceptions <= BASEL_YELLOW_MAX:
        return "amarela"
    return "vermelha"


ComputeFn = Callable[[dict, dict, dict], dict]


def compute_rolling_var_1day(
    compute: ComputeFn,
    params: dict,
    value_series: np.ndarray,
    rolling_window: int = DEFAULT_ROLLING_WINDOW,
    portfolio_inputs: list[dict] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """VaR de 1 dia recalculado em cada ponto `t >= rolling_window`, usando
    os `rolling_window` retornos imediatamente anteriores a `t` e o snapshot
    da carteira em `t`. Não depende do holding period — cada holding period só
    reescala este resultado por √h (convenção documentada, §Action 08).

    `portfolio_inputs`, quando fornecido, é o mesmo formato usado pelas
    Actions 06/07 (`portfolio_history.build_portfolio_input`) — `{"value":
    ..., "positions": [...]}` — necessário para métricas de exposição por
    posição (ex.: SA-CCR), que levantam `KeyError('positions')` se só
    receberem o valor agregado. Se omitido, cai no formato legado
    `{"value": ...}` (métricas puramente agregadas, ex.: VaR paramétrico)."""
    if len(value_series) <= rolling_window:
        raise ValueError(f"value_series (n={len(value_series)}) precisa ter mais que rolling_window ({rolling_window}) pontos")

    returns = np.diff(value_series) / value_series[:-1]
    n = len(value_series)

    indices = []
    var_1day = []
    for t in range(rolling_window, n):
        window_returns = returns[t - rolling_window : t].tolist()
        if portfolio_inputs is not None:
            portfolio_input = portfolio_inputs[t]
        else:
            portfolio_input = {"value": float(value_series[t])}
        result = compute(portfolio_input, {"returns": window_returns}, params)
        indices.append(t)
        var_1day.append(float(result["valor"]))
    return np.array(indices), np.array(var_1day)


def backtest_for_holding_period(
    value_series: np.ndarray,
    indices: np.ndarray,
    var_1day: np.ndarray,
    holding_period: int,
    confidence: float,
    alpha: float = SIGNIFICANCE_ALPHA,
) -> dict:
    """Escala VaR_1day para `holding_period` dias por raiz do tempo (convenção
    de mercado — §Action 08: "a Action 02 deve indicar a regra de
    escalonamento... ou essa é uma lacuna a decidir por convenção") e roda
    Kupiec/Christoffersen/semáforo contra o P&L realizado em janelas
    SOBREPOSTAS de `holding_period` dias (única forma de ter amostra
    suficiente para holding periods longos com 1000 dias de histórico — viola
    i.i.d., é uma limitação conhecida e reportada, não escondida)."""
    if holding_period < 1:
        raise ValueError("holding_period deve ser >= 1")

    n = len(value_series)
    usable_mask = indices <= (n - 1 - holding_period)
    usable_idx = indices[usable_mask]
    if len(usable_idx) == 0:
        raise ValueError(f"nenhuma observação utilizável para holding_period={holding_period} com os dados disponíveis")

    var_h = var_1day[usable_mask] * math.sqrt(holding_period)
    realized_loss = -(value_series[usable_idx + holding_period] - value_series[usable_idx])
    exceedances = (realized_loss > var_h).tolist()

    n_obs = len(exceedances)
    n_exceptions = int(sum(exceedances))

    kupiec = kupiec_pof_test(n_obs, n_exceptions, confidence, alpha)
    christoffersen = christoffersen_independence_test(exceedances, alpha) if n_obs >= 2 else None
    cobertura_condicional = (
        christoffersen_conditional_coverage(kupiec, christoffersen, alpha) if christoffersen is not None else None
    )

    semaforo_window = min(250, n_obs)
    n_exceptions_window = int(sum(exceedances[-semaforo_window:])) if semaforo_window > 0 else 0
    semaforo = basel_traffic_light(n_exceptions_window)

    result = {
        "holding_period": holding_period,
        "n_obs": n_obs,
        "n_exceptions": n_exceptions,
        "kupiec": kupiec,
        "christoffersen": christoffersen,
        "cobertura_condicional": cobertura_condicional,
        "semaforo": semaforo,
        "semaforo_janela_dias": semaforo_window,
        "semaforo_e_canonico": holding_period == 1,
    }
    if holding_period == 1:
        # Série completa só para h=1 (uso canônico do semáforo, §Action 08) —
        # é o que alimenta o gráfico de exceções do relatório final (§9.2)
        # sem exigir recálculo fora de `memory/state.db`. Para holding periods
        # maiores a série cresceria sem trazer um gráfico adicional pedido
        # pela spec, então fica de fora para não inchar o JSON persistido.
        result["series"] = {
            "indices": usable_idx.tolist(),
            "var_h": var_h.tolist(),
            "realized_loss": realized_loss.tolist(),
            "exceedances": exceedances,
        }
    return result
