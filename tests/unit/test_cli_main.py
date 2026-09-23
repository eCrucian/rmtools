from __future__ import annotations

from src.llm.fake_client import FakeLLMClient
from src.pipeline import __main__ as cli


def test_main_runs_pipeline_and_prints_summary(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "get_llm_client", lambda: FakeLLMClient())

    doc = tmp_path / "modelo.md"
    doc.write_text("# VaR\n\nDescrição.", encoding="utf-8")
    db_path = tmp_path / "state.db"

    exit_code = cli.main(["--doc", str(doc), "--run-id", "cli_run", "--db", str(db_path)])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "run_id=cli_run" in out
    assert "01_ingest_documentation: success" in out
    assert db_path.exists()


def test_main_reads_norm_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "get_llm_client", lambda: FakeLLMClient())

    doc = tmp_path / "modelo.md"
    doc.write_text("# SA-CCR\n\nDescrição.", encoding="utf-8")
    norm = tmp_path / "norma.txt"
    norm.write_text("texto da norma BCBS d279...", encoding="utf-8")
    db_path = tmp_path / "state.db"

    exit_code = cli.main(
        ["--doc", str(doc), "--norm", str(norm), "--run-id", "cli_run2", "--db", str(db_path), "--force"]
    )

    assert exit_code == 0


def test_main_generates_run_id_when_not_given(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "get_llm_client", lambda: FakeLLMClient())
    db_path = tmp_path / "state.db"

    exit_code = cli.main(["--db", str(db_path)])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert out.startswith("run_id=run_")
