from __future__ import annotations

import math

from src.portfolio import factors as f
from src.portfolio.base_portfolio import POSITIONS, POSITIONS_BY_ID
from src.portfolio.data_access import load_all_risk_factors
from src.portfolio.portfolio_history import (
    build_portfolio_input,
    compute_portfolio_input_series,
    compute_portfolio_returns,
    compute_portfolio_value_series,
)


def test_compute_portfolio_value_series_full_book():
    series = compute_portfolio_value_series()
    assert len(series) == f.N_OBSERVATIONS
    assert series.notna().all()
    assert all(math.isfinite(v) for v in series)


def test_compute_portfolio_returns_full_book():
    returns = compute_portfolio_returns()
    assert len(returns) == f.N_OBSERVATIONS - 1
    assert returns.notna().all()


def test_compute_portfolio_value_series_accepts_custom_positions():
    single_position = [POSITIONS_BY_ID[1]]
    series = compute_portfolio_value_series(single_position)
    assert len(series) == f.N_OBSERVATIONS
    assert series.notna().all()


def test_build_portfolio_input_shape():
    factors = load_all_risk_factors()
    market = {name: float(s.iloc[-1]) for name, s in factors.items()}

    portfolio_input = build_portfolio_input(POSITIONS, market)

    assert "value" in portfolio_input
    assert "positions" in portfolio_input
    assert len(portfolio_input["positions"]) == len(POSITIONS)
    assert math.isclose(portfolio_input["value"], sum(p["mtm_value"] for p in portfolio_input["positions"]))

    by_id = {p["id"]: p for p in portfolio_input["positions"]}
    assert by_id[1]["maturity_years"] is None  # LFT não tem tenor_years
    assert by_id[2]["maturity_years"] == 8.0  # NTN-B
    assert by_id[1]["asset_class_saccr"] == "interest_rate"
    assert by_id[8]["asset_class_saccr"] == "equity"
    assert by_id[12]["asset_class_saccr"] == "fx"
    assert by_id[21]["asset_class_saccr"] == "commodity"
    assert by_id[5]["asset_class_saccr"] == "credit"


def test_build_portfolio_input_accepts_custom_positions():
    factors = load_all_risk_factors()
    market = {name: float(s.iloc[-1]) for name, s in factors.items()}

    portfolio_input = build_portfolio_input([POSITIONS_BY_ID[1]], market)
    assert len(portfolio_input["positions"]) == 1


def test_compute_portfolio_input_series_one_snapshot_per_date():
    snapshots = compute_portfolio_input_series()

    assert len(snapshots) == f.N_OBSERVATIONS
    first, last = snapshots[0], snapshots[-1]
    for snapshot in (first, last):
        assert "value" in snapshot and "positions" in snapshot
        assert len(snapshot["positions"]) == len(POSITIONS)
    # snapshots devem variar no tempo (fatores de risco não são constantes)
    assert first["value"] != last["value"]


def test_compute_portfolio_input_series_accepts_custom_positions():
    snapshots = compute_portfolio_input_series([POSITIONS_BY_ID[1]])
    assert len(snapshots) == f.N_OBSERVATIONS
    assert len(snapshots[0]["positions"]) == 1
