from __future__ import annotations

import pytest

from src.pipeline.actions import _metric_loader


def test_load_compute_function_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        _metric_loader.load_compute_function(tmp_path / "nao_existe.py", "m")


def test_load_compute_function_success(tmp_path):
    path = tmp_path / "m.py"
    path.write_text("def compute(portfolio, risk_factors, params):\n    return {'valor': 1.0}\n", encoding="utf-8")

    compute = _metric_loader.load_compute_function(path, "m")

    assert callable(compute)
    assert compute({"value": 0}, {"returns": []}, {}) == {"valor": 1.0}


def test_load_compute_function_missing_compute_raises(tmp_path):
    path = tmp_path / "m.py"
    path.write_text("def outra_coisa():\n    return 1\n", encoding="utf-8")

    with pytest.raises(AttributeError):
        _metric_loader.load_compute_function(path, "m")


def test_load_compute_function_non_callable_compute_raises(tmp_path):
    path = tmp_path / "m.py"
    path.write_text("compute = 42\n", encoding="utf-8")

    with pytest.raises(AttributeError):
        _metric_loader.load_compute_function(path, "m")


def test_load_compute_function_spec_load_failure_raises_import_error(tmp_path, monkeypatch):
    path = tmp_path / "m.py"
    path.write_text("def compute(portfolio, risk_factors, params):\n    return {'valor': 1.0}\n", encoding="utf-8")

    monkeypatch.setattr(_metric_loader.importlib.util, "spec_from_file_location", lambda *a, **k: None)

    with pytest.raises(ImportError):
        _metric_loader.load_compute_function(path, "m")
