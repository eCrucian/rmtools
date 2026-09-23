from __future__ import annotations

import json

from src.llm.fake_client import FakeLLMClient
from src.pipeline.actions import action_06_codegen, action_08_backtest
from src.pipeline.contracts import ActionResult
from tests.conftest import make_ctx

_GOOD_SOURCE = (
    "def compute(portfolio, risk_factors, params):\n"
    "    import statistics\n"
    "    sigma = statistics.pstdev(risk_factors['returns']) if risk_factors['returns'] else 0.0\n"
    "    z = 2.33\n"
    "    return {'valor': z * sigma * portfolio['value']}\n"
)


def test_no_modules_is_skipped(memory, fake_llm):
    codegen_result = ActionResult(status="needs_human_review", output={"modules": []})
    ctx = make_ctx(memory, fake_llm, results={"06_generate_reference_code": codegen_result})

    result = action_08_backtest.run(ctx)

    assert result.status == "skipped"
    assert result.output["holding_periods"] == []


def _metric() -> dict:
    return {
        "nome": "VaR",
        "formulas": [{"expressao": "VaR = z * sigma * V", "variaveis": {}}],
        "parametros": [{"nome": "nivel_confianca", "valor_definido": True, "valor": 0.99}],
    }


def _generate_real_module(memory, tmp_path, monkeypatch):
    monkeypatch.setattr(action_06_codegen, "METRICS_DIR", tmp_path / "metrics")
    llm = FakeLLMClient(responses=[_GOOD_SOURCE])
    ctx06 = make_ctx(memory, llm, results={"02_extract_model_spec": ActionResult(status="success", output={"metrics": [_metric()]})})
    codegen_result = action_06_codegen.run(ctx06)
    assert codegen_result.status == "success"
    return codegen_result


def test_full_backtest_run_against_real_generated_module(memory, fake_llm, tmp_path, monkeypatch):
    codegen_result = _generate_real_module(memory, tmp_path, monkeypatch)
    ctx = make_ctx(memory, fake_llm, results={"06_generate_reference_code": codegen_result})

    result = action_08_backtest.run(ctx)

    assert result.status == "success"
    assert len(result.output["holding_periods"]) == 6  # 1 métrica x 6 holding periods

    holding_periods_seen = {r["holding_period"] for r in result.output["holding_periods"]}
    assert holding_periods_seen == {1, 10, 30, 60, 90, 180}

    for row in result.output["holding_periods"]:
        assert row["metrica"] == "VaR"
        assert "kupiec" in row and "lr_stat" in row["kupiec"]
        assert row["semaforo"] in ("verde", "amarela", "vermelha")
        assert row["n_obs"] > 0

    h1 = next(r for r in result.output["holding_periods"] if r["holding_period"] == 1)
    h180 = next(r for r in result.output["holding_periods"] if r["holding_period"] == 180)
    assert h1["semaforo_e_canonico"] is True
    assert h180["semaforo_e_canonico"] is False
    assert h180["n_obs"] < h1["n_obs"]  # holding periods maiores descartam observações no fim da série

    stored = memory.read_outputs("backtest_results", "run_test")
    assert len(stored) == 6

    decisions = memory.get_decisions("run_test")
    assert any(d["campo_afetado"] == "backtest.overlapping_windows" and d["criticidade"] == "media" for d in decisions)
    assert any("escalonamento_holding_period" in d["campo_afetado"] for d in decisions)


def test_writes_one_json_file_per_holding_period(memory, fake_llm, tmp_path, monkeypatch):
    codegen_result = _generate_real_module(memory, tmp_path, monkeypatch)
    ctx = make_ctx(memory, fake_llm, results={"06_generate_reference_code": codegen_result})

    action_08_backtest.run(ctx)

    from src.pipeline.actions import _common

    test_dir = _common.REPORT_DIR / "tests" / "run_test" / "08_backtesting"
    json_files = list(test_dir.glob("*.json"))
    assert len(json_files) == 6

    sample = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert sample["action_id"] == "08_backtesting"
    assert sample["metric"] == "VaR"
    assert "holding_period" in sample["data_used"]
    assert sample["data_used"]["overlapping_windows"] is True


def test_insufficient_history_needs_human_review(memory, fake_llm, tmp_path, monkeypatch):
    codegen_result = _generate_real_module(memory, tmp_path, monkeypatch)

    import pandas as pd

    from src.portfolio import portfolio_history

    short_series = pd.Series([100.0] * 50)
    monkeypatch.setattr(portfolio_history, "compute_portfolio_value_series", lambda *a, **k: short_series)

    ctx = make_ctx(memory, fake_llm, results={"06_generate_reference_code": codegen_result})
    result = action_08_backtest.run(ctx)

    assert result.status == "needs_human_review"
    assert result.output["holding_periods"] == []
    assert any("janela mínima" in note for note in result.notes)


def test_boundary_history_exactly_at_rolling_window_is_flagged_pending(memory, fake_llm, tmp_path, monkeypatch):
    """len(value_series) == janela_minima (250) passa a checagem externa
    (`< 250`), mas compute_rolling_var_1day exige estritamente MAIS que
    rolling_window (250) pontos — expõe esse caso de borda em vez de estourar."""
    codegen_result = _generate_real_module(memory, tmp_path, monkeypatch)

    import pandas as pd

    from src.portfolio import portfolio_history

    boundary_series = pd.Series([100.0] * 250)
    monkeypatch.setattr(portfolio_history, "compute_portfolio_value_series", lambda *a, **k: boundary_series)

    ctx = make_ctx(memory, fake_llm, results={"06_generate_reference_code": codegen_result})
    result = action_08_backtest.run(ctx)

    assert result.status == "needs_human_review"
    assert result.output["holding_periods"] == []
    assert any("Pendentes" in note for note in result.notes)
    decisions = memory.get_decisions("run_test")
    assert any(d["campo_afetado"] == "VaR.backtest" for d in decisions)


def test_holding_period_without_enough_data_is_silently_skipped(memory, fake_llm, tmp_path, monkeypatch):
    codegen_result = _generate_real_module(memory, tmp_path, monkeypatch)
    monkeypatch.setattr(action_08_backtest, "_load_backtest_config", lambda: (250, (1, 100_000)))

    ctx = make_ctx(memory, fake_llm, results={"06_generate_reference_code": codegen_result})
    result = action_08_backtest.run(ctx)

    assert result.status == "success"
    holding_periods_seen = {r["holding_period"] for r in result.output["holding_periods"]}
    assert holding_periods_seen == {1}  # 100_000 não tem observação utilizável e foi pulado


_SACCR_LIKE_SOURCE = (
    "def compute(portfolio, risk_factors, params):\n"
    "    total_notional = sum(abs(p['notional']) for p in portfolio['positions'])\n"
    "    return {'valor': 0.01 * total_notional}\n"
)


def test_backtest_run_against_module_requiring_positions(memory, fake_llm, tmp_path, monkeypatch):
    """Regressão: uma métrica de exposição por posição (ex.: SA-CCR), cujo
    `compute()` lê `portfolio['positions']`, não pode fazer a Action 08
    inteira falhar com `KeyError('positions')` — bug real encontrado rodando
    a fixture doc_boa (SA-CCR) ao vivo contra Ollama."""
    monkeypatch.setattr(action_06_codegen, "METRICS_DIR", tmp_path / "metrics")
    llm = FakeLLMClient(responses=[_SACCR_LIKE_SOURCE])
    ctx06 = make_ctx(memory, llm, results={"02_extract_model_spec": ActionResult(status="success", output={"metrics": [_metric()]})})
    codegen_result = action_06_codegen.run(ctx06)
    assert codegen_result.status == "success"

    ctx = make_ctx(memory, fake_llm, results={"06_generate_reference_code": codegen_result})
    result = action_08_backtest.run(ctx)

    assert result.status == "success"
    assert len(result.output["holding_periods"]) == 6
    for row in result.output["holding_periods"]:
        assert row["metrica"] == "VaR"


def test_extract_confidence_finds_keyword_match():
    from src.pipeline.actions import action_08_backtest as ab

    class _FakeMemory:
        def log_decision(self, **kwargs):
            raise AssertionError("não deveria logar decisão quando o parâmetro é encontrado")

    class _FakeCtx:
        memory = _FakeMemory()
        run_id = "run_test"

    confidence = ab._extract_confidence(_FakeCtx(), "VaR", {"nível de confiança": 0.975})
    assert confidence == 0.975


def test_extract_confidence_defaults_and_logs_decision(memory, fake_llm):
    from src.pipeline.actions import action_08_backtest as ab

    ctx = make_ctx(memory, fake_llm)
    confidence = ab._extract_confidence(ctx, "VaR", {"janela": 252})

    assert confidence == ab.be.DEFAULT_CONFIDENCE
    decisions = memory.get_decisions("run_test")
    assert any(d["campo_afetado"] == "VaR.backtest.nivel_confianca" for d in decisions)
