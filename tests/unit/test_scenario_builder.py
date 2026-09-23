from __future__ import annotations

import numpy as np
import pytest

from src.portfolio import scenario_builder as sb
from src.portfolio.base_portfolio import POSITIONS


def test_directional_variant_invalid_keep_raises():
    with pytest.raises(ValueError):
        sb.directional_variant(keep=0)


def test_directional_variant_keep_long_zeros_only_the_single_short():
    variant = sb.directional_variant(keep=1)
    zeroed_ids = {p.id for p in variant if p.notional == 0.0}
    assert zeroed_ids == {25}  # NMD é a única posição direction=-1


def test_directional_variant_keep_short_zeros_all_but_nmd():
    variant = sb.directional_variant(keep=-1)
    nonzero_ids = {p.id for p in variant if p.notional > 0.0}
    assert nonzero_ids == {25}


def test_directional_variant_does_not_mutate_original():
    sb.directional_variant(keep=1)
    assert all(p.notional > 0 for p in POSITIONS)  # original intacto


def test_concentrated_variant_unknown_factor_raises():
    with pytest.raises(ValueError):
        sb.concentrated_variant(factor_name="fator_inexistente")


def test_concentrated_variant_keeps_only_positions_using_factor():
    variant = sb.concentrated_variant(factor_name="usdbrl")
    kept_ids = {p.id for p in variant if p.notional > 0}
    expected_ids = {p.id for p in POSITIONS if "usdbrl" in p.risk_factors}
    assert kept_ids == expected_ids


def test_short_and_long_tenor_variants_partition_positions_with_tenor():
    short = sb.short_tenor_variant(threshold_years=3.0)
    long = sb.long_tenor_variant(threshold_years=3.0)
    for s, l, orig in zip(short, long, POSITIONS):
        tenor = orig.params.get("tenor_years")
        if tenor is None:
            assert s.notional == 0.0 and l.notional == 0.0
        elif tenor < 3.0:
            assert s.notional == orig.notional and l.notional == 0.0
        else:
            assert l.notional == orig.notional and s.notional == 0.0


def test_high_optionality_variant_scales_only_target_ids():
    variant = sb.high_optionality_variant(scale=4.0)
    by_id = {p.id: p for p in variant}
    for orig in POSITIONS:
        if orig.id in sb.HIGH_OPTIONALITY_IDS:
            assert by_id[orig.id].notional == orig.notional * 4.0
        else:
            assert by_id[orig.id].notional == orig.notional


def test_nmd_stress_market_invalid_direction_raises():
    with pytest.raises(ValueError):
        sb.nmd_stress_market({"nmd_decay_rate": 0.15}, direction="lateral")


def test_nmd_stress_market_alongamento_reduces_decay_rate():
    market = {"nmd_decay_rate": 0.15}
    stressed = sb.nmd_stress_market(market, direction="alongamento", multiplier=0.5)
    assert stressed["nmd_decay_rate"] == 0.30
    assert market["nmd_decay_rate"] == 0.15  # não mutou o original


def test_nmd_stress_market_encurtamento_increases_decay_rate():
    stressed = sb.nmd_stress_market({"nmd_decay_rate": 0.15}, direction="encurtamento", multiplier=2.0)
    assert stressed["nmd_decay_rate"] == 0.30


def test_prepayment_stress_market_invalid_direction_raises():
    with pytest.raises(ValueError):
        sb.prepayment_stress_market({"cpr": 0.12}, direction="lateral")


def test_prepayment_stress_market_alta_increases_cpr():
    stressed = sb.prepayment_stress_market({"cpr": 0.12}, direction="alta", multiplier=1.5)
    assert stressed["cpr"] == 0.18


def test_prepayment_stress_market_baixa_decreases_cpr():
    stressed = sb.prepayment_stress_market({"cpr": 0.12}, direction="baixa", multiplier=1.5)
    assert abs(stressed["cpr"] - 0.08) < 1e-9


def test_stressed_correlation_matrix_shape_and_diagonal():
    from src.portfolio import factors as f

    corr = sb.stressed_correlation_matrix(target_off_diagonal=0.90)
    n = len(f.FACTOR_NAMES)
    assert corr.shape == (n, n)
    assert np.allclose(np.diag(corr), 1.0)
    assert np.linalg.eigvalsh(corr).min() >= -1e-8
    off_diag_mean = (corr.sum() - n) / (n * n - n)
    assert off_diag_mean > 0.5  # deve continuar bem mais correlacionado que o base case


def test_generate_correlation_break_dataset_shape():
    series = sb.generate_correlation_break_dataset(seed=5, n_obs=40, target_off_diagonal=0.9)
    from src.portfolio import factors as f

    assert set(series) == set(f.FACTOR_NAMES)
    assert all(len(s) == 40 for s in series.values())
