from __future__ import annotations

from src.pipeline.actions import action_10_report
from tests.conftest import make_ctx


def test_report_written_from_memory_only(memory, fake_llm, tmp_path, monkeypatch):
    monkeypatch.setattr(action_10_report, "REPORT_DIR", tmp_path / "report")

    memory.log_decision(
        run_id="run_test",
        action_id="02_extract_model_spec",
        campo_afetado="janela_estimacao",
        ambiguidade_encontrada="Parâmetro sem valor definido.",
        decisao_tomada="Assumida convenção de mercado.",
        justificativa="doc não define.",
        fonte_da_decisao="convenção de mercado",
        criticidade="alta",
    )
    memory.log_decision(
        run_id="run_test",
        action_id="02_extract_model_spec",
        campo_afetado="nivel_confianca",
        ambiguidade_encontrada="Não especificado.",
        decisao_tomada="99%.",
        justificativa="padrão de mercado para VaR regulatório.",
        fonte_da_decisao="convenção de mercado",
        criticidade="media",
    )

    ctx = make_ctx(memory, fake_llm)
    result = action_10_report.run(ctx)

    assert result.status == "success"
    assert result.output["decisions_total"] == 2
    assert result.output["decisions_alta"] == 1

    report_path = tmp_path / "report" / "final_report_run_test.md"
    assert report_path.exists()
    content = report_path.read_text(encoding="utf-8")
    assert "Relatório de Validação Independente" in content
    assert "janela_estimacao" in content
    assert "Criticidade: alta (1)" in content
    assert result.artifacts == [report_path]


def test_report_handles_empty_run_gracefully(memory, fake_llm, tmp_path, monkeypatch):
    monkeypatch.setattr(action_10_report, "REPORT_DIR", tmp_path / "report")

    ctx = make_ctx(memory, fake_llm)
    result = action_10_report.run(ctx)

    assert result.status == "success"
    assert result.output["decisions_total"] == 0
    report_path = tmp_path / "report" / "final_report_run_test.md"
    assert "nenhum" in report_path.read_text(encoding="utf-8").lower() or "N/D" in report_path.read_text(encoding="utf-8")
