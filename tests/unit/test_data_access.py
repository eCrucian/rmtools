from __future__ import annotations

import pytest

from src.portfolio import data_access as da
from src.portfolio import factors as f


def test_load_risk_factor_reads_frozen_csv():
    series = da.load_risk_factor("di_pre")
    assert len(series) == f.N_OBSERVATIONS
    assert series.name == "di_pre"


def test_load_risk_factor_missing_file_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(da, "DATA_DIR", tmp_path)
    with pytest.raises(FileNotFoundError):
        da.load_risk_factor("nao_existe")


def test_load_all_risk_factors_returns_every_factor():
    series = da.load_all_risk_factors()
    assert set(series) == set(f.FACTOR_NAMES)
    assert all(len(s) == f.N_OBSERVATIONS for s in series.values())


def test_load_correlation_matrix_shape():
    corr = da.load_correlation_matrix()
    assert corr.shape == (len(f.FACTOR_NAMES), len(f.FACTOR_NAMES))


def test_load_correlation_matrix_missing_file_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(da, "DATA_DIR", tmp_path)
    with pytest.raises(FileNotFoundError):
        da.load_correlation_matrix()
