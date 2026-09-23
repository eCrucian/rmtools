from __future__ import annotations

from src.pipeline.actions import _common


def test_frozen_portfolio_available_false_when_dir_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(_common, "DATA_DIR", tmp_path / "data")
    assert _common.frozen_portfolio_available() is False


def test_frozen_portfolio_available_false_when_dir_empty(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    (data_dir / "risk_factors").mkdir(parents=True)
    monkeypatch.setattr(_common, "DATA_DIR", data_dir)
    assert _common.frozen_portfolio_available() is False


def test_frozen_portfolio_available_true_when_csv_present(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    risk_factors = data_dir / "risk_factors"
    risk_factors.mkdir(parents=True)
    (risk_factors / "di_pre.csv").write_text("date,value\n2024-01-01,10.5\n", encoding="utf-8")
    monkeypatch.setattr(_common, "DATA_DIR", data_dir)
    assert _common.frozen_portfolio_available() is True


def test_sha256_bytes_is_deterministic():
    assert _common.sha256_bytes(b"abc") == _common.sha256_bytes(b"abc")
    assert _common.sha256_bytes(b"abc") != _common.sha256_bytes(b"abd")
    assert _common.sha256_bytes(b"abc").startswith("sha256:")


def test_load_prompt_template_reads_real_file():
    text = _common.load_prompt_template("02_extract_model_spec", "extract.md")
    assert "{texto}" in text
