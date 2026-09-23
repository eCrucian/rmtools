"""Motor de testes de estabilidade (CLAUDE.md §Action 07).

Perturba fatores de risco em `data/risk_factors/` (congelados, só-leitura),
reprecifica a carteira base via `pricing_models.price_portfolio` (ground
truth determinístico — não o código gerado) e monta o snapshot completo de
`portfolio` (§Action 06 — `{"value": ..., "positions": [...]}`,
`portfolio_history.build_portfolio_input`), e observa como o VALOR DA
MÉTRICA GERADA (Action 06) responde à mudança daí resultante:
`compute(portfolio_choque, {"returns": ...}, params)`.

Simplificação documentada: a série de retornos históricos usada como insumo
de volatilidade (`risk_factors["returns"]`) não é recalculada por choque
(custaria reprecificar os 1000 dias a cada um dos ~106 cenários) — só
`portfolio["value"]`/`portfolio["positions"]` refletem o choque. Isso é
suficiente para testar elasticidade/estabilidade do CÓDIGO GERADO em resposta
a uma mudança de valor/exposição da carteira, que é exatamente o que a
Action 06 pode calcular a partir da especificação textual da métrica.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from src.portfolio import factors as f
from src.portfolio.pricing_models import price_portfolio
from src.portfolio.portfolio_history import build_portfolio_input

ComputeFn = Callable[[dict, dict, dict], dict]

DEFAULT_BOUNDS = {
    "fator_explosao_max": 50.0,
    "insensibilidade_min_pct": 0.001,
    "desvio_linearidade_max": 0.20,
}
INSENSIBILIDADE_SHOCK_THRESHOLD = 0.10


@dataclass
class StabilityTestResult:
    metrica: str
    cenario: str  # "isolado" | "conjunto" | "quebra_correlacao"
    fator: str
    choque: float | None
    valor_base: float
    valor_choque: float
    delta_metrica: float
    elasticidade: float | None
    flag: str  # "ok" | "explosao" | "insensivel" | "nao_linear" | "indeterminado_base_zero"
    dentro_do_limite: bool


def shock_market(market: dict[str, float], factor_name: str | None, shock_pct: float) -> dict[str, float]:
    """`factor_name=None` aplica o choque a TODOS os fatores (choque conjunto)."""
    shocked = dict(market)
    names = [factor_name] if factor_name is not None else list(shocked)
    for name in names:
        shocked[name] = shocked[name] * (1.0 + shock_pct)
    return shocked


def classify_elasticity(
    valor_base: float,
    valor_choque: float,
    shock_pct: float,
    reference_elasticity: float | None = None,
    bounds: dict | None = None,
) -> tuple[float | None, str, bool]:
    """`reference_elasticity` é a elasticidade já observada no MENOR choque
    testado para o MESMO fator — não um valor universal como 1.0. A
    grande maioria dos 20 fatores só influencia parcialmente o valor da
    carteira (ex.: um choque em `wti`, que nenhuma posição referencia, produz
    elasticidade ~0 — o esperado, não um desvio de "linearidade teórica").
    "Linear" aqui significa que a elasticidade se MANTÉM ESTÁVEL conforme o
    choque cresce (proporcionalidade), não que ela vale algum número fixo."""
    bounds = bounds or DEFAULT_BOUNDS
    delta = valor_choque - valor_base

    if valor_base == 0:
        if abs(delta) < 1e-9:
            return None, "ok", True
        return None, "indeterminado_base_zero", True

    delta_pct = delta / valor_base
    elasticidade = delta_pct / shock_pct if shock_pct != 0 else None
    if elasticidade is None:
        return None, "ok", True

    if abs(elasticidade) > bounds.get("fator_explosao_max", 50.0):
        return elasticidade, "explosao", False
    if abs(delta_pct) < bounds.get("insensibilidade_min_pct", 0.001) and shock_pct >= INSENSIBILIDADE_SHOCK_THRESHOLD:
        return elasticidade, "insensivel", False
    if reference_elasticity is not None and abs(reference_elasticity) > 1e-9:
        relative_deviation = abs(elasticidade - reference_elasticity) / abs(reference_elasticity)
        if relative_deviation > bounds.get("desvio_linearidade_max", 0.20):
            return elasticidade, "nao_linear", False
    return elasticidade, "ok", True


def portfolio_value(positions, market: dict[str, float]) -> float:
    return sum(price_portfolio(positions, market).values())


def run_isolated_and_joint_tests(
    *,
    metrica: str,
    compute: ComputeFn,
    params: dict,
    positions,
    base_market: dict[str, float],
    base_returns: list[float],
    choques_pct: tuple[float, ...],
    bounds: dict | None = None,
    factor_names: tuple[str, ...] | None = None,
) -> list[StabilityTestResult]:
    factor_names = factor_names if factor_names is not None else tuple(f.FACTOR_NAMES)
    # Assume `choques_pct` em ordem crescente de magnitude (config/stability_bounds.yaml
    # já vem assim) — o menor choque de cada fator vira a referência de linearidade
    # para os choques maiores DO MESMO FATOR.
    ordered_choques = tuple(sorted(choques_pct, key=abs))

    valor_base = float(compute(build_portfolio_input(positions, base_market), {"returns": base_returns}, params)["valor"])

    results: list[StabilityTestResult] = []
    for factor_name in factor_names:
        reference_elasticity: float | None = None
        for shock in ordered_choques:
            shocked_market = shock_market(base_market, factor_name, shock)
            valor_choque = float(
                compute(build_portfolio_input(positions, shocked_market), {"returns": base_returns}, params)["valor"]
            )
            elasticidade, flag, ok = classify_elasticity(valor_base, valor_choque, shock, reference_elasticity, bounds)
            if reference_elasticity is None and elasticidade is not None:
                reference_elasticity = elasticidade
            results.append(
                StabilityTestResult(
                    metrica=metrica, cenario="isolado", fator=factor_name, choque=shock,
                    valor_base=valor_base, valor_choque=valor_choque, delta_metrica=valor_choque - valor_base,
                    elasticidade=elasticidade, flag=flag, dentro_do_limite=ok,
                )
            )

    reference_elasticity = None
    for shock in ordered_choques:
        shocked_market = shock_market(base_market, None, shock)
        valor_choque = float(
            compute(build_portfolio_input(positions, shocked_market), {"returns": base_returns}, params)["valor"]
        )
        elasticidade, flag, ok = classify_elasticity(valor_base, valor_choque, shock, reference_elasticity, bounds)
        if reference_elasticity is None and elasticidade is not None:
            reference_elasticity = elasticidade
        results.append(
            StabilityTestResult(
                metrica=metrica, cenario="conjunto", fator="TODOS", choque=shock,
                valor_base=valor_base, valor_choque=valor_choque, delta_metrica=valor_choque - valor_base,
                elasticidade=elasticidade, flag=flag, dentro_do_limite=ok,
            )
        )
    return results


def run_correlation_break_test(
    *,
    metrica: str,
    compute: ComputeFn,
    params: dict,
    positions,
    base_market: dict[str, float],
    base_returns: list[float],
    stressed_market: dict[str, float],
    bounds: dict | None = None,
) -> StabilityTestResult:
    """Cenário herdado da Action 04 (§Action 07 — "rodar também o cenário de
    quebra de correlação"): reprecifica sob um snapshot vindo de um dataset
    gerado com a matriz de correlação estressada (`scenario_builder`), em vez
    de um choque percentual num único fator."""
    valor_base = float(compute(build_portfolio_input(positions, base_market), {"returns": base_returns}, params)["valor"])
    valor_choque = float(
        compute(build_portfolio_input(positions, stressed_market), {"returns": base_returns}, params)["valor"]
    )
    # Não há "choque_pct" único aqui (a mudança vem de uma estrutura de
    # correlação diferente, não de um multiplicador) — reporta o delta
    # relativo como referência, sem aplicar o gate de linearidade/explosão
    # (que pressupõe uma magnitude de choque conhecida).
    delta = valor_choque - valor_base
    return StabilityTestResult(
        metrica=metrica, cenario="quebra_correlacao", fator="TODOS", choque=None,
        valor_base=valor_base, valor_choque=valor_choque, delta_metrica=delta,
        elasticidade=None, flag="informativo", dentro_do_limite=True,
    )
