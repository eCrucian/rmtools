from __future__ import annotations

from src.portfolio import factors as f
from src.portfolio import pricing_models as pm
from src.portfolio.base_portfolio import BANKING_BOOK_POSITION_IDS, POSITIONS, POSITIONS_BY_ID


def test_exactly_26_positions_with_unique_sequential_ids():
    assert len(POSITIONS) == 26
    ids = [p.id for p in POSITIONS]
    assert ids == list(range(1, 27))


def test_positions_by_id_lookup():
    for p in POSITIONS:
        assert POSITIONS_BY_ID[p.id] is p


def test_currencies_are_supported():
    assert {p.currency for p in POSITIONS} <= {"BRL", "USD"}


def test_directions_are_plus_or_minus_one():
    assert {p.direction for p in POSITIONS} <= {1, -1}


def test_all_risk_factors_are_known_factor_names():
    known = set(f.FACTOR_NAMES)
    for p in POSITIONS:
        unknown = set(p.risk_factors) - known
        assert not unknown, f"posição {p.id} referencia fator(es) desconhecido(s): {unknown}"


def test_all_pricers_are_registered():
    for p in POSITIONS:
        assert p.pricer in pm.PRICERS, f"posição {p.id} usa pricer não registrado: {p.pricer}"


def test_banking_book_ids_exist_and_match_expected():
    assert BANKING_BOOK_POSITION_IDS == (23, 25, 26)
    for pid in BANKING_BOOK_POSITION_IDS:
        assert pid in POSITIONS_BY_ID


def test_nmd_is_the_only_explicit_liability():
    liabilities = [p.id for p in POSITIONS if p.direction == -1]
    assert liabilities == [25]
