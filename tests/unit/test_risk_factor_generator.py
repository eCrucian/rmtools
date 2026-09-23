from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.portfolio import factors as f
from src.portfolio import risk_factor_generator as gen


def test_generate_risk_factors_shapes_and_determinism():
    series_a = gen.generate_risk_factors(seed=123, n_obs=50)
    series_b = gen.generate_risk_factors(seed=123, n_obs=50)

    assert set(series_a) == set(f.FACTOR_NAMES)
    for name, s in series_a.items():
        assert len(s) == 50
        assert not s.isna().any()
        pd.testing.assert_series_equal(s, series_b[name])


def test_generate_risk_factors_different_seed_diverges():
    series_a = gen.generate_risk_factors(seed=1, n_obs=50)
    series_b = gen.generate_risk_factors(seed=2, n_obs=50)
    assert not series_a["di_pre"].equals(series_b["di_pre"])


def test_cir_series_never_negative():
    series = gen.generate_risk_factors(seed=7, n_obs=200)
    for name in list(f.SPREADS) + list(f.BEHAVIORAL):
        assert (series[name] >= 0).all(), f"{name} teve valor negativo"


def test_vasicek_series_respects_floor():
    series = gen.generate_risk_factors(seed=7, n_obs=200)
    for name, params in f.CURVES.items():
        assert (series[name] >= params.floor - 1e-9).all()


def test_gbm_series_stays_strictly_positive():
    series = gen.generate_risk_factors(seed=7, n_obs=200)
    for name in f.SPOTS:
        assert (series[name] > 0).all()


def test_vol_series_stays_strictly_positive():
    series = gen.generate_risk_factors(seed=7, n_obs=200)
    for name in f.VOLS:
        assert (series[name] > 0).all()


def test_custom_correlation_matrix_changes_output():
    default_series = gen.generate_risk_factors(seed=42, n_obs=100)
    stressed_corr = np.full((len(f.FACTOR_NAMES), len(f.FACTOR_NAMES)), 0.95)
    np.fill_diagonal(stressed_corr, 1.0)
    stressed_series = gen.generate_risk_factors(seed=42, n_obs=100, correlation_matrix=stressed_corr)

    assert not default_series["ibov"].equals(stressed_series["ibov"])


def test_generate_correlation_matrix_df_shape_and_labels():
    df = gen.generate_correlation_matrix_df()
    assert list(df.index) == f.FACTOR_NAMES
    assert list(df.columns) == f.FACTOR_NAMES
    assert df.shape == (len(f.FACTOR_NAMES), len(f.FACTOR_NAMES))


def test_freeze_writes_expected_files(tmp_path):
    gen.freeze(output_dir=tmp_path, seed=99, n_obs=30)

    for name in f.FACTOR_NAMES:
        csv_path = tmp_path / f"{name}.csv"
        assert csv_path.exists()
        df = pd.read_csv(csv_path)
        assert list(df.columns) == ["date", "value"]
        assert len(df) == 30

    corr_path = tmp_path / "correlation_matrix.csv"
    assert corr_path.exists()
    corr_df = pd.read_csv(corr_path, index_col=0)
    assert corr_df.shape == (len(f.FACTOR_NAMES), len(f.FACTOR_NAMES))


def test_main_requires_freeze_flag():
    with pytest.raises(SystemExit):
        gen.main([])


def test_main_freeze_writes_to_output_dir(tmp_path, capsys):
    exit_code = gen.main(["--freeze", "--output-dir", str(tmp_path)])
    assert exit_code == 0
    assert (tmp_path / "di_pre.csv").exists()
    out = capsys.readouterr().out
    assert "congelados" in out
