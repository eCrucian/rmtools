from __future__ import annotations

import pytest

from src.memory.db import MemoryStore


@pytest.fixture
def store(tmp_path):
    with MemoryStore(tmp_path / "state.db") as s:
        yield s


def test_start_and_finish_run(store):
    store.start_run("r1", doc_source="doc.md", backend_llm="ollama")
    run = store.get_run("r1")
    assert run["status"] == "running"

    store.finish_run("r1", "success")
    run = store.get_run("r1")
    assert run["status"] == "success"
    assert run["finished_at"] is not None


def test_get_run_missing_returns_none(store):
    assert store.get_run("nao-existe") is None


def test_record_document(store):
    store.start_run("r1", None, "ollama")
    store.record_document("r1", "doc.md", "sha256:abc", ".md", is_code_example=False, sections=["intro"])
    # sem query dedicada em MemoryStore — valida via SQL direto (auditável)
    row = store.conn.execute("SELECT * FROM documents WHERE run_id = ?", ("r1",)).fetchone()
    assert row["file_path"] == "doc.md"
    assert row["is_code_example"] == 0


def test_log_decision_and_get_decisions_filtered(store):
    store.start_run("r1", None, "ollama")
    store.log_decision("r1", "02_extract_model_spec", "campo", "ambiguidade", "decisao", "justificativa", "convenção de mercado", "alta")
    store.log_decision("r1", "02_extract_model_spec", "campo2", "ambiguidade2", "decisao2", "justificativa2", "referência X", "baixa")

    all_decisions = store.get_decisions("r1")
    assert len(all_decisions) == 2

    only_alta = store.get_decisions("r1", criticidade="alta")
    assert len(only_alta) == 1
    assert only_alta[0]["campo_afetado"] == "campo"


def test_log_decision_rejects_invalid_criticidade(store):
    store.start_run("r1", None, "ollama")
    with pytest.raises(ValueError):
        store.log_decision("r1", "02", "campo", "amb", "dec", "just", "fonte", "crítico-demais")


def test_write_and_read_outputs_roundtrip(store):
    store.start_run("r1", None, "ollama")
    store.write_output("extractions", "r1", "02_extract_model_spec", {"metrics": [{"nome": "VaR"}]})

    outputs = store.read_outputs("extractions", "r1")
    assert len(outputs) == 1
    assert outputs[0]["data"]["metrics"][0]["nome"] == "VaR"


def test_write_output_accepts_dataclass_payload(store):
    from dataclasses import dataclass

    @dataclass
    class Payload:
        nome: str
        nota: float

    store.start_run("r1", None, "ollama")
    store.write_output("quality_scores", "r1", "03_assess_doc_quality", Payload(nome="escopo", nota=3.0))

    outputs = store.read_outputs("quality_scores", "r1")
    assert outputs[0]["data"] == {"nome": "escopo", "nota": 3.0}


def test_write_output_rejects_unknown_table(store):
    with pytest.raises(ValueError):
        store.write_output("tabela_inventada", "r1", "action", {})


def test_read_outputs_rejects_unknown_table(store):
    with pytest.raises(ValueError):
        store.read_outputs("tabela_inventada", "r1")


def test_record_code_version(store):
    store.start_run("r1", None, "ollama")
    store.record_code_version("r1", "06_generate_reference_code", "VaR", "src/metrics/var.py", "sha256:xyz", diff="+def compute(): ...")
    row = store.conn.execute("SELECT * FROM code_versions WHERE run_id = ?", ("r1",)).fetchone()
    assert row["metric"] == "VaR"


def test_checkpoint_save_and_get(store):
    from src.pipeline.contracts import ActionResult

    store.start_run("r1", None, "ollama")
    result = ActionResult(status="success", output={"a": 1}, artifacts=[], notes=["ok"])
    store.save_action_result("r1", "01_ingest_documentation", "hash123", result)

    cached = store.get_checkpoint("r1", "01_ingest_documentation", "hash123")
    assert cached["status"] == "success"
    assert cached["output"] == {"a": 1}

    assert store.get_checkpoint("r1", "01_ingest_documentation", "hash-diferente") is None


def test_get_all_action_runs(store):
    from src.pipeline.contracts import ActionResult

    store.start_run("r1", None, "ollama")
    store.save_action_result("r1", "01_ingest_documentation", "h1", ActionResult(status="success"))
    store.save_action_result("r1", "02_extract_model_spec", "h2", ActionResult(status="needs_human_review"))

    all_runs = store.get_all_action_runs("r1")
    assert [r["action_id"] for r in all_runs] == ["01_ingest_documentation", "02_extract_model_spec"]
