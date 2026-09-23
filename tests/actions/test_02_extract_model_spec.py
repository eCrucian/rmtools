from __future__ import annotations

from src.llm.fake_client import FakeLLMClient
from src.pipeline.actions import action_02_extract
from src.pipeline.contracts import ActionResult
from tests.conftest import make_ctx


def _ingest_result(text: str) -> ActionResult:
    return ActionResult(status="success", output={"methodological_text": text, "documents": [], "has_code_example": False})


def test_empty_methodological_text_needs_human_review(memory, fake_llm):
    ctx = make_ctx(memory, fake_llm, results={"01_ingest_documentation": _ingest_result("")})
    result = action_02_extract.run(ctx)

    assert result.status == "needs_human_review"
    assert result.output["metrics"] == []


def test_valid_extraction_logs_gap_for_undefined_param(memory):
    llm = FakeLLMClient(
        responses=[
            {
                "metrics": [
                    {
                        "nome": "VaR paramétrico",
                        "variacoes": ["gaussiano"],
                        "formulas": [{"expressao": "VaR = z*sigma*sqrt(t)", "variaveis": {}}],
                        "hipoteses": {"explicitas": ["normalidade"], "implicitas": []},
                        "parametros": [
                            {"nome": "janela_estimacao", "valor_definido": False, "valor": None, "descricao": "janela"}
                        ],
                        "escopo_declarado": {"produtos": [], "carteiras": [], "moedas": []},
                        "tipo": "interno_proprietario",
                    }
                ]
            }
        ]
    )
    ctx = make_ctx(memory, llm, results={"01_ingest_documentation": _ingest_result("VaR paramétrico com janela não definida.")})

    result = action_02_extract.run(ctx)

    assert result.status == "success"
    assert len(result.output["metrics"]) == 1
    decisions = memory.get_decisions("run_test")
    assert any("janela_estimacao" in d["campo_afetado"] for d in decisions)
    extractions = memory.read_outputs("extractions", "run_test")
    assert len(extractions) == 1


def test_defined_param_does_not_log_a_decision(memory):
    llm = FakeLLMClient(
        responses=[
            {
                "metrics": [
                    {
                        "nome": "VaR paramétrico",
                        "variacoes": [],
                        "formulas": [],
                        "hipoteses": {"explicitas": [], "implicitas": []},
                        "parametros": [
                            {"nome": "nivel_confianca", "valor_definido": True, "valor": "99%", "descricao": "nível"}
                        ],
                        "escopo_declarado": {"produtos": [], "carteiras": [], "moedas": []},
                        "tipo": "interno_proprietario",
                    }
                ]
            }
        ]
    )
    ctx = make_ctx(memory, llm, results={"01_ingest_documentation": _ingest_result("VaR paramétrico com nível de confiança de 99%.")})

    result = action_02_extract.run(ctx)

    assert result.status == "success"
    decisions = memory.get_decisions("run_test")
    assert decisions == []


def test_invalid_llm_response_needs_human_review(memory):
    llm = FakeLLMClient(responses=["isso não é JSON", "ainda não é JSON", "continua não sendo JSON"])
    ctx = make_ctx(memory, llm, results={"01_ingest_documentation": _ingest_result("texto qualquer")})

    result = action_02_extract.run(ctx)

    assert result.status == "needs_human_review"
    decisions = memory.get_decisions("run_test")
    assert any(d["campo_afetado"] == "extracao_geral" for d in decisions)
    calls = memory.conn.execute("SELECT COUNT(*) FROM llm_calls WHERE run_id = ?", ("run_test",)).fetchone()[0]
    assert calls == 1
