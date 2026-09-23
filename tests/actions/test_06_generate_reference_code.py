from __future__ import annotations

from pathlib import Path

import pytest

from src.llm.fake_client import FakeLLMClient
from src.pipeline.actions import action_06_codegen
from src.pipeline.contracts import ActionResult
from tests.conftest import make_ctx

_GOOD_SOURCE = (
    "def compute(portfolio, risk_factors, params):\n"
    "    import statistics\n"
    "    sigma = statistics.pstdev(risk_factors['returns']) if risk_factors['returns'] else 0.0\n"
    "    z = params.get('nivel_confianca_z', 2.33)\n"
    "    return {'valor': z * sigma * portfolio['value']}\n"
)

_BAD_SOURCE_MISSING_VALOR = "def compute(portfolio, risk_factors, params):\n    return {'outro_campo': 1.0}\n"

_BAD_SOURCE_FORBIDDEN_IMPORT = (
    "import socket\ndef compute(portfolio, risk_factors, params):\n    return {'valor': 1.0}\n"
)


def _metric(nome: str = "VaR Paramétrico", parametros: list[dict] | None = None) -> dict:
    return {
        "nome": nome,
        "formulas": [{"expressao": "VaR = z * sigma * V", "variaveis": {}}],
        "parametros": parametros if parametros is not None else [
            {"nome": "nivel_confianca", "valor_definido": True, "valor": 0.99, "descricao": "nível de confiança"}
        ],
    }


def _extraction_result(metrics: list[dict]) -> ActionResult:
    return ActionResult(status="success", output={"metrics": metrics})


def test_no_metrics_needs_human_review(memory, fake_llm):
    ctx = make_ctx(memory, fake_llm, results={"02_extract_model_spec": _extraction_result([])})
    result = action_06_codegen.run(ctx)

    assert result.status == "needs_human_review"
    assert result.output["modules"] == []


def test_without_frozen_portfolio_blocks_codegen_honestly(memory, fake_llm, monkeypatch):
    monkeypatch.setattr(action_06_codegen, "frozen_portfolio_available", lambda: False)
    ctx = make_ctx(memory, fake_llm, results={"02_extract_model_spec": _extraction_result([_metric()])})

    result = action_06_codegen.run(ctx)

    assert result.status == "needs_human_review"
    assert "VaR Paramétrico" in result.output["metrics_pendentes"]
    assert any("bloqueada" in note for note in result.notes)


def test_successful_generation_writes_module_and_records_version(memory, tmp_path, monkeypatch):
    monkeypatch.setattr(action_06_codegen, "METRICS_DIR", tmp_path / "metrics")
    llm = FakeLLMClient(responses=[_GOOD_SOURCE])
    ctx = make_ctx(memory, llm, results={"02_extract_model_spec": _extraction_result([_metric()])})

    result = action_06_codegen.run(ctx)

    assert result.status == "success"
    assert len(result.output["modules"]) == 1
    module = result.output["modules"][0]
    assert module["attempts"] == 1
    assert Path(module["path"]).exists()
    assert Path(module["path"]).read_text(encoding="utf-8") == _GOOD_SOURCE.strip()
    assert result.artifacts == [Path(module["path"])]

    versions = memory.conn.execute("SELECT * FROM code_versions WHERE run_id = ?", ("run_test",)).fetchall()
    assert len(versions) == 1
    assert versions[0]["metric"] == "VaR Paramétrico"


def test_generation_retries_after_sandbox_rejection_then_succeeds(memory, tmp_path, monkeypatch):
    monkeypatch.setattr(action_06_codegen, "METRICS_DIR", tmp_path / "metrics")
    llm = FakeLLMClient(responses=[_BAD_SOURCE_MISSING_VALOR, _GOOD_SOURCE])
    ctx = make_ctx(memory, llm, results={"02_extract_model_spec": _extraction_result([_metric()])})

    result = action_06_codegen.run(ctx)

    assert result.status == "success"
    assert result.output["modules"][0]["attempts"] == 2
    decisions = memory.get_decisions("run_test")
    assert any(d["criticidade"] == "baixa" and "tentativa_1" in d["campo_afetado"] for d in decisions)


def test_generation_exhausts_attempts_and_reports_pending(memory, tmp_path, monkeypatch):
    monkeypatch.setattr(action_06_codegen, "METRICS_DIR", tmp_path / "metrics")
    llm = FakeLLMClient(responses=[_BAD_SOURCE_MISSING_VALOR] * action_06_codegen.MAX_ATTEMPTS)
    ctx = make_ctx(memory, llm, results={"02_extract_model_spec": _extraction_result([_metric()])})

    result = action_06_codegen.run(ctx)

    assert result.status == "needs_human_review"
    assert result.output["modules"] == []
    assert result.output["metrics_pendentes"] == ["VaR Paramétrico"]
    decisions = memory.get_decisions("run_test")
    final_attempt_decisions = [d for d in decisions if f"tentativa_{action_06_codegen.MAX_ATTEMPTS}" in d["campo_afetado"]]
    assert any(d["criticidade"] == "media" for d in final_attempt_decisions)


def test_forbidden_import_is_rejected_and_retried(memory, tmp_path, monkeypatch):
    monkeypatch.setattr(action_06_codegen, "METRICS_DIR", tmp_path / "metrics")
    llm = FakeLLMClient(responses=[_BAD_SOURCE_FORBIDDEN_IMPORT, _GOOD_SOURCE])
    ctx = make_ctx(memory, llm, results={"02_extract_model_spec": _extraction_result([_metric()])})

    result = action_06_codegen.run(ctx)

    assert result.status == "success"


def test_partial_success_across_multiple_metrics(memory, tmp_path, monkeypatch):
    monkeypatch.setattr(action_06_codegen, "METRICS_DIR", tmp_path / "metrics")
    llm = FakeLLMClient(
        responses=[_GOOD_SOURCE] + [_BAD_SOURCE_MISSING_VALOR] * action_06_codegen.MAX_ATTEMPTS
    )
    metrics = [_metric("VaR Paramétrico"), _metric("VaR Histórico")]
    ctx = make_ctx(memory, llm, results={"02_extract_model_spec": _extraction_result(metrics)})

    result = action_06_codegen.run(ctx)

    assert result.status == "needs_human_review"
    assert len(result.output["modules"]) == 1
    assert result.output["metrics_pendentes"] == ["VaR Histórico"]


def test_undefined_param_with_known_convention_gets_default(memory, tmp_path, monkeypatch):
    monkeypatch.setattr(action_06_codegen, "METRICS_DIR", tmp_path / "metrics")
    metric = _metric(parametros=[{"nome": "janela de estimação", "valor_definido": False, "valor": None}])
    llm = FakeLLMClient(responses=[_GOOD_SOURCE])
    ctx = make_ctx(memory, llm, results={"02_extract_model_spec": _extraction_result([metric])})

    action_06_codegen.run(ctx)

    decisions = memory.get_decisions("run_test")
    assert any(d["criticidade"] == "media" and "janela" in d["justificativa"].lower() for d in decisions)


def test_undefined_param_without_convention_logged_as_alta(memory, tmp_path, monkeypatch):
    monkeypatch.setattr(action_06_codegen, "METRICS_DIR", tmp_path / "metrics")
    metric = _metric(parametros=[{"nome": "fator misterioso", "valor_definido": False, "valor": None}])
    llm = FakeLLMClient(responses=[_GOOD_SOURCE])
    ctx = make_ctx(memory, llm, results={"02_extract_model_spec": _extraction_result([metric])})

    action_06_codegen.run(ctx)

    decisions = memory.get_decisions("run_test")
    assert any(d["criticidade"] == "alta" and "fator misterioso" in d["campo_afetado"] for d in decisions)


def test_defined_param_does_not_log_decision(memory, tmp_path, monkeypatch):
    monkeypatch.setattr(action_06_codegen, "METRICS_DIR", tmp_path / "metrics")
    llm = FakeLLMClient(responses=[_GOOD_SOURCE])
    ctx = make_ctx(memory, llm, results={"02_extract_model_spec": _extraction_result([_metric()])})

    action_06_codegen.run(ctx)

    decisions = memory.get_decisions("run_test")
    assert decisions == []


# --------------------------------------------------------------------------
# Helpers puros
# --------------------------------------------------------------------------

def test_normalize_param_value_brazilian_decimal():
    assert action_06_codegen._normalize_param_value("1,4") == 1.4


def test_normalize_param_value_brazilian_percent():
    assert action_06_codegen._normalize_param_value("4,00%") == pytest.approx(0.04)


def test_normalize_param_value_integer_string():
    assert action_06_codegen._normalize_param_value("0") == 0.0


def test_normalize_param_value_thousands_separator():
    assert action_06_codegen._normalize_param_value("1.234,56") == pytest.approx(1234.56)


def test_normalize_param_value_already_numeric_is_unchanged():
    assert action_06_codegen._normalize_param_value(0.99) == 0.99
    assert action_06_codegen._normalize_param_value(5) == 5


def test_normalize_param_value_multi_value_table_string_is_unchanged():
    # tabela com vários valores — nunca deve ser tratada como um único número
    table = "0,50% (Juros), 4,00% (Câmbio), 0,46% (Crédito)"
    assert action_06_codegen._normalize_param_value(table) == table


def test_normalize_param_value_non_numeric_string_is_unchanged():
    assert action_06_codegen._normalize_param_value("curva interna da mesa") == "curva interna da mesa"


def test_normalize_param_value_none_is_unchanged():
    assert action_06_codegen._normalize_param_value(None) is None


def test_resolve_params_normalizes_defined_brazilian_values(memory, fake_llm):
    ctx = make_ctx(memory, fake_llm)
    parametros = [
        {"nome": "alpha", "valor_definido": True, "valor": "1,4"},
        {"nome": "SF_fx", "valor_definido": True, "valor": "4,00%"},
    ]
    resolved = action_06_codegen._resolve_params(ctx, "EAD", parametros)

    assert resolved["alpha"] == 1.4
    assert resolved["SF_fx"] == pytest.approx(0.04)


def test_sanitize_module_name_basic():
    assert action_06_codegen._sanitize_module_name("VaR Paramétrico") == "var_param_trico"


def test_sanitize_module_name_leading_digit():
    assert action_06_codegen._sanitize_module_name("99% VaR").startswith("m_")


def test_sanitize_module_name_empty_falls_back():
    assert action_06_codegen._sanitize_module_name("!!!") == "metrica_sem_nome"


def test_strip_markdown_fences_with_language_tag():
    text = "```python\ndef compute():\n    pass\n```"
    assert action_06_codegen._strip_markdown_fences(text) == "def compute():\n    pass"


def test_strip_markdown_fences_without_fences_is_noop():
    text = "def compute():\n    pass"
    assert action_06_codegen._strip_markdown_fences(text) == text


def test_strip_markdown_fences_unclosed_fence():
    text = "```python\ndef compute():\n    pass"
    assert action_06_codegen._strip_markdown_fences(text) == "def compute():\n    pass"
