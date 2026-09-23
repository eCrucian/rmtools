from __future__ import annotations

import pytest

from src.llm.fake_client import FakeLLMClient
from src.memory.db import MemoryStore
from src.pipeline.contracts import RunContext


@pytest.fixture(autouse=True)
def _isolate_report_dir(monkeypatch, tmp_path):
    """Impede que qualquer teste (mesmo indiretamente, via run_pipeline até a
    Action 10 ou via a CLI) escreva report/final_report_*.md no repositório de
    verdade. Testes que querem inspecionar o caminho explicitamente (ex.:
    tests/actions/test_10_replicability_report.py) podem sobrescrever de novo
    com seu próprio monkeypatch — o último setattr na mesma chave vence."""
    from src.pipeline.actions import action_10_report

    monkeypatch.setattr(action_10_report, "REPORT_DIR", tmp_path / "report")


@pytest.fixture(autouse=True)
def _isolate_metrics_dir(monkeypatch, tmp_path):
    """Mesma lógica para src/metrics/*.py escrito pela Action 06 — nunca
    grava no repositório de verdade durante os testes."""
    from src.pipeline.actions import action_06_codegen

    monkeypatch.setattr(action_06_codegen, "METRICS_DIR", tmp_path / "metrics")


@pytest.fixture(autouse=True)
def _isolate_common_report_dir(monkeypatch, tmp_path):
    """A Action 07 resolve `report_dir` via `_common.REPORT_DIR` em tempo de
    chamada (não um default de função, que ficaria congelado no import) —
    isola isso separadamente das duas fixtures acima."""
    from src.pipeline.actions import _common

    monkeypatch.setattr(_common, "REPORT_DIR", tmp_path / "report")


@pytest.fixture
def memory(tmp_path):
    store = MemoryStore(tmp_path / "state.db")
    store.start_run("run_test", doc_source=None, backend_llm="fake")
    yield store
    store.close()


@pytest.fixture
def fake_llm():
    return FakeLLMClient()


def make_ctx(memory, llm_client, inputs=None, results=None, force=False) -> RunContext:
    return RunContext(
        run_id="run_test",
        memory=memory,
        llm_client=llm_client,
        inputs=inputs or {},
        results=results or {},
        force=force,
    )
