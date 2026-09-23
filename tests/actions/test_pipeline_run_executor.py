"""Testes do executor do pipeline (src/pipeline/run.py) — plumbing/infra:
ordenação, skip automático de dependentes em falha, e resumabilidade via
checkpoint. Não re-testa a lógica de negócio de cada action (isso vive nos
tests/actions/test_<id>.py individuais)."""

from __future__ import annotations

from src.llm.fake_client import FakeLLMClient
from src.memory.db import MemoryStore
from src.pipeline.contracts import ActionResult
from src.pipeline.registry import ACTIONS
from src.pipeline.run import run_pipeline


_VALID_METRIC_SOURCE = "def compute(portfolio, risk_factors, params):\n    return {'valor': portfolio['value']}\n"


def _queue_for_full_traversal() -> list[dict | str]:
    # Uma resposta por chamada de LLM esperada ao longo do pipeline (02, 03, 04, 06)
    # quando não há norma anexada (05 é skipped sem chamar o LLM). A resposta de 06
    # já é um código válido de primeira tentativa, para não gastar retries/subprocessos
    # à toa nestes testes de infraestrutura do executor (a lógica de retry da Action 06
    # já tem cobertura própria em tests/actions/test_06_generate_reference_code.py).
    return [
        {"metrics": [{"nome": "VaR", "parametros": [], "tipo": "interno_proprietario"}]},  # 02
        {"itens": [], "nota_agregada": 2.0},  # 03
        {
            "hipoteses_avaliadas": [],
            "comparacao_metodologia_desafiante": {},
            "limitacoes_discutidas": [],
            "referencias_citadas": [],
        },  # 04
        _VALID_METRIC_SOURCE,  # 06
    ]


def test_full_run_reaches_action_10_without_a_document(tmp_path):
    memory = MemoryStore(tmp_path / "state.db")
    llm = FakeLLMClient()
    results = run_pipeline(run_id="r1", memory=memory, llm_client=llm, inputs={"doc_paths": []})

    assert list(results.keys()) == list(ACTIONS.keys())
    assert results["01_ingest_documentation"].status == "needs_human_review"
    assert results["10_replicability_report"].status == "success"
    run_row = memory.get_run("r1")
    assert run_row["status"] == "success"  # nenhuma action com status "failed"
    memory.close()


def test_failed_action_skips_dependents_but_not_the_whole_pipeline(tmp_path, monkeypatch):
    def _boom(ctx):
        raise RuntimeError("bug do agente, não lacuna de doc")

    monkeypatch.setattr(ACTIONS["02_extract_model_spec"], "run", _boom)

    memory = MemoryStore(tmp_path / "state.db")
    llm = FakeLLMClient()
    results = run_pipeline(run_id="r2", memory=memory, llm_client=llm, inputs={"doc_paths": []})

    assert results["02_extract_model_spec"].status == "failed"
    for dependent in ("03_assess_doc_quality", "04_assess_methodology", "05_regulatory_adherence", "06_generate_reference_code"):
        assert results[dependent].status == "skipped"
    # Action 10 depende (indiretamente) de tudo, mas roda mesmo assim — ela
    # mesma não falha, só reporta o que tinha disponível.
    assert results["10_replicability_report"].status == "success"
    memory.close()


def test_action_10_always_runs_even_when_its_own_direct_dependency_fails(tmp_path, monkeypatch):
    """Regressão de um bug real encontrado num smoke test contra Ollama: a
    Action 03 (dependência DIRETA de 10, não só de 02) estourou uma exceção de
    rede de verdade (timeout), e a Action 10 foi pulada por tabela — a run
    terminou sem relatório final nenhum, violando a regra central do
    CLAUDE.md de que o pipeline sempre produz um relatório."""

    def _boom(ctx):
        raise RuntimeError("timeout real do backend de LLM")

    monkeypatch.setattr(ACTIONS["03_assess_doc_quality"], "run", _boom)

    memory = MemoryStore(tmp_path / "state.db")
    llm = FakeLLMClient()
    results = run_pipeline(run_id="r6", memory=memory, llm_client=llm, inputs={"doc_paths": []})

    assert results["03_assess_doc_quality"].status == "failed"
    assert results["10_replicability_report"].status == "success"
    memory.close()


def test_cached_failed_checkpoint_still_propagates_skip_on_rerun(tmp_path, monkeypatch):
    def _boom(ctx):
        raise RuntimeError("bug do agente")

    monkeypatch.setattr(ACTIONS["02_extract_model_spec"], "run", _boom)

    memory = MemoryStore(tmp_path / "state.db")
    llm = FakeLLMClient()
    inputs = {"doc_paths": []}

    run_pipeline(run_id="r5", memory=memory, llm_client=llm, inputs=inputs)
    # Segunda execução: 02 já tem checkpoint com status "failed" e será servido
    # do cache (sem invocar _boom de novo) — o skip de dependentes precisa
    # continuar funcionando mesmo vindo do cache.
    results = run_pipeline(run_id="r5", memory=memory, llm_client=llm, inputs=inputs, force=False)

    assert results["02_extract_model_spec"].status == "failed"
    assert results["03_assess_doc_quality"].status == "skipped"
    memory.close()


def test_resumability_skips_llm_calls_on_rerun_without_force(tmp_path):
    doc = tmp_path / "modelo.md"
    doc.write_text("# VaR paramétrico\n\nDescrição do modelo.", encoding="utf-8")

    memory = MemoryStore(tmp_path / "state.db")
    llm = FakeLLMClient(responses=list(_queue_for_full_traversal()))
    inputs = {"doc_paths": [str(doc)]}

    run_pipeline(run_id="r3", memory=memory, llm_client=llm, inputs=inputs)
    calls_after_first_run = len(llm.calls)
    assert calls_after_first_run > 0

    run_pipeline(run_id="r3", memory=memory, llm_client=llm, inputs=inputs, force=False)
    assert len(llm.calls) == calls_after_first_run  # nada foi recalculado

    memory.close()


def test_force_recomputes_even_when_checkpoint_exists(tmp_path):
    doc = tmp_path / "modelo.md"
    doc.write_text("# VaR paramétrico\n\nDescrição do modelo.", encoding="utf-8")

    memory = MemoryStore(tmp_path / "state.db")
    llm = FakeLLMClient(responses=list(_queue_for_full_traversal()) * 2)
    inputs = {"doc_paths": [str(doc)]}

    run_pipeline(run_id="r4", memory=memory, llm_client=llm, inputs=inputs)
    calls_after_first_run = len(llm.calls)

    run_pipeline(run_id="r4", memory=memory, llm_client=llm, inputs=inputs, force=True)
    assert len(llm.calls) > calls_after_first_run

    memory.close()
