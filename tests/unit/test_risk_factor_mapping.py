from __future__ import annotations

import pytest

from src.portfolio import risk_factor_mapping as rfm
from src.portfolio.base_portfolio import POSITIONS


def test_get_risk_factors_matches_position_data():
    for p in POSITIONS:
        assert rfm.get_risk_factors(p.id) == p.risk_factors


def test_get_risk_factors_unknown_id_raises():
    with pytest.raises(KeyError):
        rfm.get_risk_factors(999)


def test_positions_using_factor_di_pre_includes_lft():
    assert 1 in rfm.positions_using_factor("di_pre")


def test_positions_using_factor_unused_factor_returns_empty():
    assert rfm.positions_using_factor("wti") == []


def test_all_factors_used_is_subset_of_factor_names():
    from src.portfolio import factors as f

    assert rfm.all_factors_used() <= set(f.FACTOR_NAMES)


def test_build_mapping_table_has_one_row_per_position():
    table = rfm.build_mapping_table()
    assert len(table) == len(POSITIONS)
    assert table[0]["risk_factors"] == ", ".join(POSITIONS[0].risk_factors)


def test_positions_for_scope_full_book():
    assert len(rfm.positions_for_scope()) == 26


def test_positions_for_scope_banking_book_only():
    banking = rfm.positions_for_scope(banking_book_only=True)
    assert {p.id for p in banking} == {23, 25, 26}
