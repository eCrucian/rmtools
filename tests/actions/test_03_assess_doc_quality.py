from __future__ import annotations

from src.llm.fake_client import FakeLLMClient
from src.pipeline.actions import action_03_quality
from src.pipeline.contracts import ActionResult
from tests.conftest import make_ctx

_FULL_RUBRIC_RESPONSE = {
    "itens": [
        {"item": "escopo_de_aplicacao", "nota": 4, "evidencia": "seção 1"},
        {"item": "proposta_do_modelo", "nota": 4, "evidencia": "seção 2"},
        {"item": "desenvolvimento_metodologico", "nota": 3, "evidencia": "seção 3"},
        {"item": "declaracao_e_teste_de_hipoteses", "nota": 3, "evidencia": "seção 4"},
        {"item": "limitacoes", "nota": 2, "evidencia": "seção 5"},
        {"item": "motivacao_do_modelo", "nota": 3, "evidencia": "seção 6"},
        {"item": "codigo_exemplo_anexo", "nota": 4, "evidencia": "anexo A"},
    ],
    "nota_agregada": 3.28,
    "gaps_priorizados": [],
}


def _ingest_result(text: str) -> ActionResult:
    return ActionResult(status="success", output={"methodological_text": text, "documents": [], "has_code_example": False})


def test_empty_text_needs_human_review(memory, fake_llm):
    ctx = make_ctx(memory, fake_llm, results={"01_ingest_documentation": _ingest_result("")})
    result = action_03_quality.run(ctx)

    assert result.status == "needs_human_review"
    assert result.output["nota_agregada"] == 0.0


def test_full_rubric_written_to_memory(memory):
    llm = FakeLLMClient(responses=[_FULL_RUBRIC_RESPONSE])
    ctx = make_ctx(memory, llm, results={"01_ingest_documentation": _ingest_result("doc bem escrita")})

    result = action_03_quality.run(ctx)

    assert result.status == "success"
    # 3.29 = média real de [4,4,3,3,2,3,4]/7, recalculada — NÃO o 3.28 que o
    # LLM "reportou" (a Action 03 nunca confia na aritmética do modelo).
    assert result.output["nota_agregada"] == 3.29
    assert len(result.output["itens"]) == 7
    stored = memory.read_outputs("quality_scores", "run_test")
    assert stored[0]["data"]["nota_agregada"] == 3.29


def test_nota_agregada_is_recomputed_never_trusted_from_llm(memory):
    """Reproduz o caso real observado com qwen3:4b: o modelo reporta uma
    nota_agregada que não bate com a média das próprias notas por item."""
    response = {
        "itens": [
            {"item": "escopo_de_aplicacao", "nota": 4, "evidencia": "s1"},
            {"item": "proposta_do_modelo", "nota": 4, "evidencia": "s2"},
            {"item": "desenvolvimento_metodologico", "nota": 4, "evidencia": "s3"},
            {"item": "declaracao_e_teste_de_hipoteses", "nota": 2, "evidencia": "s4"},
            {"item": "limitacoes", "nota": 4, "evidencia": "s5"},
            {"item": "motivacao_do_modelo", "nota": 0, "evidencia": "ausente"},
            {"item": "codigo_exemplo_anexo", "nota": 0, "evidencia": "ausente"},
        ],
        "nota_agregada": 4.0,  # errado — LLM "alucinou" a média
    }
    llm = FakeLLMClient(responses=[response])
    ctx = make_ctx(memory, llm, results={"01_ingest_documentation": _ingest_result("doc qualquer")})

    result = action_03_quality.run(ctx)

    assert result.output["nota_agregada"] != 4.0
    assert result.output["nota_agregada"] == 2.57
    assert any("divergente da média real" in note for note in result.notes)


def test_nota_agregada_consistent_llm_report_has_no_divergence_note(memory):
    llm = FakeLLMClient(responses=[_FULL_RUBRIC_RESPONSE])
    ctx = make_ctx(memory, llm, results={"01_ingest_documentation": _ingest_result("doc bem escrita")})

    result = action_03_quality.run(ctx)

    assert not any("divergente" in note for note in result.notes)


def test_missing_rubric_items_are_filled_as_ausente(memory):
    partial_response = {"itens": [{"item": "escopo_de_aplicacao", "nota": 1, "evidencia": "ausente"}], "nota_agregada": 1.0}
    llm = FakeLLMClient(responses=[partial_response])
    ctx = make_ctx(memory, llm, results={"01_ingest_documentation": _ingest_result("doc fraca")})

    result = action_03_quality.run(ctx)

    items_by_id = {i["item"]: i for i in result.output["itens"]}
    assert len(items_by_id) == 7
    assert items_by_id["limitacoes"]["evidencia"] == "ausente"


def test_invalid_llm_response_needs_human_review(memory):
    llm = FakeLLMClient(responses=["não é JSON válido"] * 3)
    ctx = make_ctx(memory, llm, results={"01_ingest_documentation": _ingest_result("doc qualquer")})

    result = action_03_quality.run(ctx)

    assert result.status == "needs_human_review"
