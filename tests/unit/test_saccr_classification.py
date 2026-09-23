from __future__ import annotations

from src.portfolio.base_portfolio import POSITIONS
from src.portfolio.saccr_classification import SACCR_ASSET_CLASS

_VALID_CLASSES = {"interest_rate", "fx", "credit", "equity", "commodity"}


def test_every_position_is_classified():
    ids = {p.id for p in POSITIONS}
    assert set(SACCR_ASSET_CLASS) == ids


def test_all_classes_are_valid_saccr_classes():
    assert set(SACCR_ASSET_CLASS.values()) <= _VALID_CLASSES


def test_all_five_classes_are_represented():
    assert set(SACCR_ASSET_CLASS.values()) == _VALID_CLASSES
