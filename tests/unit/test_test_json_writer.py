from __future__ import annotations

import json

from src.pipeline.actions._test_json import write_test_json


def test_write_test_json_creates_expected_file_and_content(tmp_path):
    path = write_test_json(
        run_id="r1",
        action_id="07_stability_tests",
        test_id="var__choque_usdbrl__5pct",
        metric="VaR",
        backend_llm="ollama",
        test_code_source="x = 1",
        test_code_file="gerado dinamicamente",
        data_used={"risk_factors": ["data/risk_factors/usdbrl.csv"], "scenario": "isolado"},
        results={"status": "pass", "valor_base": 1.0, "valor_choque": 1.05},
        notes=["nota de teste"],
        report_dir=tmp_path,
    )

    assert path.exists()
    assert path.parent == tmp_path / "tests" / "r1" / "07_stability_tests"

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["run_id"] == "r1"
    assert payload["test_id"] == "var__choque_usdbrl__5pct"
    assert payload["test_code"]["source"] == "x = 1"
    assert payload["test_code"]["hash"].startswith("sha256:")
    assert payload["results"]["valor_base"] == 1.0
    assert payload["notes"] == ["nota de teste"]


def test_write_test_json_sanitizes_unsafe_characters_in_filename(tmp_path):
    path = write_test_json(
        run_id="r1",
        action_id="07_stability_tests",
        test_id="var__choque_5%__teste",
        metric="VaR",
        backend_llm=None,
        test_code_source="",
        test_code_file="",
        data_used={},
        results={},
        report_dir=tmp_path,
    )
    assert path.name == "var__choque_5___teste.json"


def test_write_test_json_defaults_notes_to_empty_list(tmp_path):
    path = write_test_json(
        run_id="r1", action_id="a", test_id="t", metric="m", backend_llm=None,
        test_code_source="", test_code_file="", data_used={}, results={}, report_dir=tmp_path,
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["notes"] == []
