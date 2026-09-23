"""Série histórica de valor de mercado da carteira hipotética (§5), calculada
a partir dos fatores de risco congelados — nunca persistida como fixture
(diferente de `data/risk_factors/`): é barata o bastante (~1-2s para os 1000
dias) para recalcular sob demanda a cada run, e depende de `pricing_models.py`
(código, não dado), que pode evoluir sem exigir um novo freeze."""

from __future__ import annotations

import pandas as pd

from .base_portfolio import Position
from .data_access import load_all_risk_factors
from .pricing_models import price_portfolio
from .saccr_classification import SACCR_ASSET_CLASS


def compute_portfolio_value_series(positions: list[Position] | None = None) -> pd.Series:
    from .base_portfolio import POSITIONS

    positions = positions if positions is not None else POSITIONS
    factors = load_all_risk_factors()
    dates = factors[next(iter(factors))].index

    values = []
    for date in dates:
        market = {name: series.loc[date] for name, series in factors.items()}
        pvs = price_portfolio(positions, market)
        values.append(sum(pvs.values()))

    return pd.Series(values, index=dates, name="portfolio_value")


def compute_portfolio_returns(positions: list[Position] | None = None) -> pd.Series:
    """Retorno percentual diário do valor da carteira (usado como `risk_factors
    -> "returns"` na Action 06 — série que alimenta a métrica gerada)."""
    values = compute_portfolio_value_series(positions)
    return values.pct_change().dropna().rename("portfolio_return")


def compute_portfolio_input_series(positions: list[Position] | None = None) -> list[dict]:
    """Snapshot completo de carteira (mesmo formato de `build_portfolio_input`,
    incluindo `positions`) para cada uma das datas congeladas de fatores de
    risco — usado pelo backtest (Action 08) para alimentar `compute()` com o
    mesmo formato de portfolio usado pelas Actions 06/07. Métricas agregadas
    (VaR paramétrico) só leem `value`; métricas de exposição por posição
    (SA-CCR) precisam de `positions` — sem isso, `compute()` levanta
    `KeyError('positions')` para essas métricas."""
    from .base_portfolio import POSITIONS

    positions = positions if positions is not None else POSITIONS
    factors = load_all_risk_factors()
    dates = factors[next(iter(factors))].index

    snapshots = []
    for date in dates:
        market = {name: series.loc[date] for name, series in factors.items()}
        snapshots.append(build_portfolio_input(positions, market))
    return snapshots


def build_portfolio_input(positions: list[Position], market: dict[str, float]) -> dict:
    """Snapshot de carteira no formato passado como `portfolio` para
    `compute()` (§Action 06): `{"value": float, "positions": [...]}`. Métricas
    agregadas (ex.: VaR paramétrico) só usam `value`; métricas de exposição
    por contraparte (ex.: SA-CCR) precisam de `positions` — notional, classe
    de ativo (§`saccr_classification.py`), moeda, direção, prazo (quando
    aplicável — instrumentos sem tenor contratual explícito, ex. LFT/NMD/
    futuros linearizados, têm `maturity_years: null`) e MTM por posição."""
    pvs = price_portfolio(positions, market)
    position_rows = [
        {
            "id": p.id,
            "name": p.name,
            "asset_class_saccr": SACCR_ASSET_CLASS.get(p.id, "outro"),
            "currency": p.currency,
            "notional": p.notional,
            "direction": p.direction,
            "maturity_years": p.params.get("tenor_years"),
            "mtm_value": pvs[p.id],
        }
        for p in positions
    ]
    return {"value": sum(pvs.values()), "positions": position_rows}
