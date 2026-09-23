from __future__ import annotations

from src.llm.fake_client import FakeLLMClient
from src.pipeline.actions import action_05_regulatory
from src.pipeline.contracts import ActionResult
from tests.conftest import make_ctx


def _extraction_result(metrics: list[dict]) -> ActionResult:
    return ActionResult(status="success", output={"metrics": metrics})


def test_non_regulatory_model_is_skipped(memory, fake_llm):
    ctx = make_ctx(
        memory, fake_llm,
        results={"02_extract_model_spec": _extraction_result([{"nome": "VaR", "tipo": "interno_proprietario"}])},
    )
    result = action_05_regulatory.run(ctx)

    assert result.status == "skipped"
    assert result.output["motivo"] == "modelo nao regulamentado"


def test_regulatory_model_without_norm_is_skipped(memory, fake_llm):
    ctx = make_ctx(
        memory, fake_llm,
        results={"02_extract_model_spec": _extraction_result([{"nome": "SA-CCR", "tipo": "padronizado_regulatorio"}])},
        inputs={"norm_text": None},
    )
    result = action_05_regulatory.run(ctx)

    assert result.status == "skipped"
    assert result.output["motivo"] == "norma nao disponibilizada"


def test_regulatory_model_with_norm_produces_matrix(memory):
    llm = FakeLLMClient(
        responses=[
            {
                "clausulas": [
                    {
                        "clausula": "d279 §1",
                        "requisito": "Add-On por classe de ativo",
                        "tratamento_na_doc": "descrito na seção 2",
                        "aderente": True,
                        "observacao": "",
                    }
                ]
            }
        ]
    )
    ctx = make_ctx(
        memory, llm,
        results={"02_extract_model_spec": _extraction_result([{"nome": "SA-CCR", "tipo": "padronizado_regulatorio"}])},
        inputs={"norm_text": "texto da norma BCBS d279..."},
    )
    result = action_05_regulatory.run(ctx)

    assert result.status == "success"
    assert len(result.output["clausulas"]) == 1
    stored = memory.read_outputs("regulatory_adherence", "run_test")
    assert len(stored) == 1


def test_invalid_llm_response_needs_human_review(memory):
    llm = FakeLLMClient(responses=["não é JSON"] * 3)
    ctx = make_ctx(
        memory, llm,
        results={"02_extract_model_spec": _extraction_result([{"nome": "SA-CCR", "tipo": "padronizado_regulatorio"}])},
        inputs={"norm_text": "texto da norma"},
    )
    result = action_05_regulatory.run(ctx)

    assert result.status == "needs_human_review"
