from __future__ import annotations

from src.memory.db import MemoryStore
from src.pipeline.report_render import render_markdown


def test_render_markdown_with_full_data(tmp_path):
    memory = MemoryStore(tmp_path / "state.db")
    memory.start_run("r1", "modelo.md", "ollama")

    memory.write_output(
        "quality_scores",
        "r1",
        "03_assess_doc_quality",
        {"itens": [{"item": "escopo_de_aplicacao", "nota": 3, "evidencia": "seção 1"}], "nota_agregada": 3.0},
    )
    memory.write_output(
        "methodology_assessment",
        "r1",
        "04_assess_methodology",
        {
            "hipoteses_avaliadas": [{"hipotese": "normalidade", "testavel_quantitativamente": True, "justificativa_testabilidade": "ok"}],
            "limitacoes_discutidas": ["não captura caudas pesadas"],
            "referencias_citadas": [{"referencia": "Jorion", "referencia_nao_verificada": False}],
        },
    )
    memory.write_output(
        "regulatory_adherence",
        "r1",
        "05_regulatory_adherence",
        {"clausulas": [{"clausula": "d279 §1", "requisito": "Add-On", "tratamento_na_doc": "ok", "aderente": True, "observacao": ""}]},
    )
    memory.write_output(
        "stability_results",
        "r1",
        "07_stability_tests",
        {"metrica": "VaR", "fator": "usdbrl", "choque": 0.05, "delta_metrica": 0.02, "dentro_do_limite": True},
    )
    memory.write_output(
        "backtest_results",
        "r1",
        "08_backtesting",
        {"metrica": "VaR", "holding_period": 1, "kupiec": "pass", "christoffersen": "pass", "semaforo": "verde"},
    )
    memory.write_output("extended_tests", "r1", "09_extended_test_suite", {"executados": [], "pendentes": [{"id": "concentration_test"}]})
    memory.log_decision("r1", "02_extract_model_spec", "campo", "amb", "dec", "just", "convenção de mercado", "alta")

    from src.pipeline.contracts import ActionResult

    memory.save_action_result("r1", "01_ingest_documentation", "h1", ActionResult(status="success", notes=["ok"]))

    markdown = render_markdown(memory, "r1")

    assert "d279 §1" in markdown
    assert "VaR" in markdown
    assert "verde" in markdown
    assert "normalidade" in markdown
    assert "Jorion" in markdown
    assert "concentration_test" in markdown
    assert "01_ingest_documentation" in markdown

    memory.close()


def test_render_markdown_with_no_data_still_produces_report(tmp_path):
    memory = MemoryStore(tmp_path / "state.db")
    memory.start_run("r2", None, "ollama")

    markdown = render_markdown(memory, "r2")

    assert "Relatório de Validação Independente" in markdown
    assert "run `r2`" in markdown
    memory.close()
