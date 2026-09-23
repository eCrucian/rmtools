from __future__ import annotations

import sys
import types

from src.pipeline.actions import action_09_extended
from src.pipeline.contracts import ActionResult
from tests.conftest import make_ctx


def test_default_registry_runs_both_enabled_tests(memory, fake_llm):
    # Sem "07_stability_tests" em ctx.results, os dois testes habilitados por
    # padrão (concentration_test, liquidity_horizon_scaling) se auto-reportam
    # "skipped" — não há nada pendente/não-implementado no registry default.
    ctx = make_ctx(memory, fake_llm)
    result = action_09_extended.run(ctx)

    assert result.status == "success"
    ids_executados = {e["id"] for e in result.output["executados"]}
    assert ids_executados == {"concentration_test", "liquidity_horizon_scaling"}
    assert all(e["status"] == "skipped" for e in result.output["executados"])
    assert result.output["pendentes"] == []
    stored = memory.read_outputs("extended_tests", "run_test")
    assert len(stored) == 1


def test_default_registry_runs_real_tests_when_stability_results_available(memory, fake_llm):
    from src.pipeline.contracts import ActionResult as AR

    stability = AR(
        status="success",
        output={"elasticidade": [
            {"metrica": "VaR", "cenario": "isolado", "fator": "di_pre", "choque": 0.01, "delta_metrica": 5.0},
        ]},
    )
    ctx = make_ctx(memory, fake_llm, results={"07_stability_tests": stability})
    result = action_09_extended.run(ctx)

    ids_by_status = {e["id"]: e["status"] for e in result.output["executados"]}
    assert ids_by_status == {"concentration_test": "success", "liquidity_horizon_scaling": "success"}


def test_enabled_test_with_existing_module_is_executed(memory, fake_llm, monkeypatch):
    fake_module = types.ModuleType("src.tests_extended.fake_ok")
    fake_module.run = lambda ctx: ActionResult(status="success", output={"ok": True})
    monkeypatch.setitem(sys.modules, "src.tests_extended.fake_ok", fake_module)
    monkeypatch.setattr(
        action_09_extended,
        "load_yaml",
        lambda path: {"extended_tests": [{"id": "fake_ok", "enabled": True, "description": "teste fake"}]},
    )

    ctx = make_ctx(memory, fake_llm)
    result = action_09_extended.run(ctx)

    assert result.status == "success"
    assert result.output["executados"] == [{"id": "fake_ok", "status": "success", "output": {"ok": True}}]
    assert result.output["pendentes"] == []


def test_disabled_entry_is_listed_as_pending(memory, fake_llm, monkeypatch):
    monkeypatch.setattr(
        action_09_extended,
        "load_yaml",
        lambda path: {"extended_tests": [{"id": "algo_futuro", "enabled": False, "description": "planejado"}]},
    )

    ctx = make_ctx(memory, fake_llm)
    result = action_09_extended.run(ctx)

    assert result.output["executados"] == []
    assert result.output["pendentes"] == [{"id": "algo_futuro", "description": "planejado"}]


def test_enabled_test_with_missing_module_is_reported_as_pending_with_error(memory, fake_llm, monkeypatch):
    monkeypatch.setattr(
        action_09_extended,
        "load_yaml",
        lambda path: {"extended_tests": [{"id": "nao_existe", "enabled": True, "description": "sem módulo"}]},
    )

    ctx = make_ctx(memory, fake_llm)
    result = action_09_extended.run(ctx)

    assert result.output["executados"] == []
    assert result.output["pendentes"][0]["id"] == "nao_existe"
    assert "erro" in result.output["pendentes"][0]
    assert any("falhou ao importar" in note for note in result.notes)
