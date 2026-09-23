from __future__ import annotations

from src.llm.fake_client import FakeLLMClient
from src.pipeline.actions import action_04_methodology
from src.pipeline.contracts import ActionResult
from tests.conftest import make_ctx


def _extraction_result(metrics: list[dict]) -> ActionResult:
    return ActionResult(status="success", output={"metrics": metrics})


def _metric_with_hypotheses(explicitas: list[str], implicitas: list[str] | None = None) -> dict:
    return {"nome": "VaR", "hipoteses": {"explicitas": explicitas, "implicitas": implicitas or []}}


def _llm_response(referencias_nao_verificadas: bool = False) -> dict:
    return {
        "hipoteses_avaliadas": [],
        "comparacao_metodologia_desafiante": {"aplicavel": True, "alternativa_sugerida": "VaR histórico", "racional": "benchmark"},
        "limitacoes_discutidas": ["não captura caudas pesadas"],
        "referencias_citadas": [{"referencia": "Jorion — Value at Risk", "referencia_nao_verificada": referencias_nao_verificadas}],
    }


def test_no_metrics_needs_human_review(memory, fake_llm):
    ctx = make_ctx(memory, fake_llm, results={"02_extract_model_spec": _extraction_result([])})
    result = action_04_methodology.run(ctx)

    assert result.status == "needs_human_review"


def test_invalid_llm_response_needs_human_review(memory):
    llm = FakeLLMClient(responses=["não é JSON"] * 3)
    ctx = make_ctx(memory, llm, results={"02_extract_model_spec": _extraction_result([_metric_with_hypotheses(["normalidade"])])})

    result = action_04_methodology.run(ctx)

    assert result.status == "needs_human_review"


def test_unverified_reference_is_noted(memory):
    llm = FakeLLMClient(responses=[_llm_response(referencias_nao_verificadas=True)])
    ctx = make_ctx(memory, llm, results={"02_extract_model_spec": _extraction_result([_metric_with_hypotheses([])])})

    result = action_04_methodology.run(ctx)

    assert any("referência não verificada" in note for note in result.notes)


def test_hypothesis_without_matching_keyword_runs_no_quantitative_test(memory):
    llm = FakeLLMClient(responses=[_llm_response()])
    ctx = make_ctx(
        memory, llm,
        results={"02_extract_model_spec": _extraction_result([_metric_with_hypotheses(["linearidade de payoff"])])},
    )

    result = action_04_methodology.run(ctx)

    assert result.status == "success"
    assert result.output["testes_quantitativos"] == {}
    assert any("nenhum teste rodado" in note for note in result.notes)


def test_normality_hypothesis_runs_normality_test_against_default_basket(memory):
    llm = FakeLLMClient(responses=[_llm_response()])
    ctx = make_ctx(
        memory, llm,
        results={"02_extract_model_spec": _extraction_result([_metric_with_hypotheses(["retornos normalmente distribuídos"])])},
    )

    result = action_04_methodology.run(ctx)

    assert result.status == "success"
    assert "normalidade" in result.output["testes_quantitativos"]
    tested_factors = set(result.output["testes_quantitativos"]["normalidade"])
    assert tested_factors == {"di_pre", "usdbrl", "ibov"}
    for factor_result in result.output["testes_quantitativos"]["normalidade"].values():
        assert "rejects_normality" in factor_result

    decisions = memory.get_decisions("run_test")
    assert any(d["campo_afetado"] == "fatores_de_teste_hipotese" and d["criticidade"] == "media" for d in decisions)


def test_iid_hypothesis_runs_autocorrelation_test(memory):
    llm = FakeLLMClient(responses=[_llm_response()])
    ctx = make_ctx(
        memory, llm,
        results={"02_extract_model_spec": _extraction_result([_metric_with_hypotheses([], ["retornos i.i.d."])])},
    )

    result = action_04_methodology.run(ctx)

    assert "iid" in result.output["testes_quantitativos"]
    assert all("rejects_iid" in r for r in result.output["testes_quantitativos"]["iid"].values())


def test_stationarity_hypothesis_runs_stationarity_test(memory):
    llm = FakeLLMClient(responses=[_llm_response()])
    ctx = make_ctx(
        memory, llm,
        results={"02_extract_model_spec": _extraction_result([_metric_with_hypotheses(["processo estacionário"])])},
    )

    result = action_04_methodology.run(ctx)

    assert "estacionariedade" in result.output["testes_quantitativos"]
    assert all("rejects_stationarity" in r for r in result.output["testes_quantitativos"]["estacionariedade"].values())


def test_single_hypothesis_can_trigger_multiple_test_types(memory):
    llm = FakeLLMClient(responses=[_llm_response()])
    ctx = make_ctx(
        memory, llm,
        results={"02_extract_model_spec": _extraction_result([_metric_with_hypotheses(["retornos i.i.d. e normalmente distribuídos"])])},
    )

    result = action_04_methodology.run(ctx)

    assert set(result.output["testes_quantitativos"]) == {"normalidade", "iid"}


def test_quantitative_test_notes_report_rejection_counts(memory):
    llm = FakeLLMClient(responses=[_llm_response()])
    ctx = make_ctx(
        memory, llm,
        results={"02_extract_model_spec": _extraction_result([_metric_with_hypotheses(["normalidade"])])},
    )

    result = action_04_methodology.run(ctx)

    assert any(note.startswith("normalidade: rejeitada em") for note in result.notes)


def test_extract_hypothesis_texts_handles_expected_dict_shape():
    texts = action_04_methodology._extract_hypothesis_texts({"explicitas": ["A", "B"], "implicitas": ["C"]})
    assert texts == ["A", "B", "C"]


def test_extract_hypothesis_texts_handles_list_of_dicts_deviation():
    # Desvio real observado num run ao vivo (qwen3:4b, doc_boa/SA-CCR): o LLM
    # retornou uma LISTA de objetos {"explicita":..., "implicita":...} em vez
    # do dict esperado — isso não pode derrubar a action com AttributeError.
    hipoteses = [
        {"explicita": "H1: independência entre classes", "implicita": "correlação nula"},
        {"explicita": "H2: MTM representativo"},
    ]
    texts = action_04_methodology._extract_hypothesis_texts(hipoteses)
    assert texts == ["H1: independência entre classes", "correlação nula", "H2: MTM representativo"]


def test_extract_hypothesis_texts_handles_list_of_plain_strings():
    texts = action_04_methodology._extract_hypothesis_texts(["retornos i.i.d.", "normalidade"])
    assert texts == ["retornos i.i.d.", "normalidade"]


def test_extract_hypothesis_texts_handles_non_list_value_under_dict_key():
    texts = action_04_methodology._extract_hypothesis_texts({"explicitas": "uma string solta, não lista"})
    assert texts == ["uma string solta, não lista"]


def test_extract_hypothesis_texts_skips_falsy_non_list_value_under_dict_key():
    texts = action_04_methodology._extract_hypothesis_texts({"explicitas": None, "implicitas": []})
    assert texts == []


def test_extract_hypothesis_texts_skips_falsy_items_in_list():
    texts = action_04_methodology._extract_hypothesis_texts(["texto válido", "", None])
    assert texts == ["texto válido"]


def test_extract_hypothesis_texts_handles_unexpected_shape_without_crashing():
    assert action_04_methodology._extract_hypothesis_texts("texto solto qualquer") == []
    assert action_04_methodology._extract_hypothesis_texts(None) == []
    assert action_04_methodology._extract_hypothesis_texts(42) == []


def test_run_with_hipoteses_as_list_of_dicts_does_not_crash(memory):
    """Regressão do crash real: Action 04 rodando fim-a-fim com `hipoteses`
    no formato desviante (lista de dicts) não deve levantar AttributeError."""
    metric = {
        "nome": "EAD",
        "hipoteses": [{"explicita": "retornos normalmente distribuídos e i.i.d."}],
    }
    llm = FakeLLMClient(responses=[_llm_response()])
    ctx = make_ctx(memory, llm, results={"02_extract_model_spec": _extraction_result([metric])})

    result = action_04_methodology.run(ctx)

    assert result.status == "success"
    assert set(result.output["testes_quantitativos"]) == {"normalidade", "iid"}


def test_run_quantitative_tests_ignores_unrecognized_test_type(memory, fake_llm):
    ctx = make_ctx(memory, fake_llm)
    results = action_04_methodology._run_quantitative_tests(ctx, {"tipo_desconhecido"})

    assert results == {"tipo_desconhecido": {}}


def test_written_to_memory(memory):
    llm = FakeLLMClient(responses=[_llm_response()])
    ctx = make_ctx(memory, llm, results={"02_extract_model_spec": _extraction_result([_metric_with_hypotheses(["normalidade"])])})

    action_04_methodology.run(ctx)

    stored = memory.read_outputs("methodology_assessment", "run_test")
    assert len(stored) == 1
    assert "testes_quantitativos" in stored[0]["data"]
