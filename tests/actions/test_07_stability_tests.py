from __future__ import annotations

import json

from src.llm.fake_client import FakeLLMClient
from src.pipeline.actions import action_06_codegen, action_07_stability
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

    result = action_07_stability.run(ctx)

    assert result.status == "skipped"
    assert result.output["elasticidade"] == []


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


def test_full_stability_run_against_real_generated_module(memory, fake_llm, tmp_path, monkeypatch):
    codegen_result = _generate_real_module(memory, tmp_path, monkeypatch)
    ctx = make_ctx(memory, fake_llm, results={"06_generate_reference_code": codegen_result})

    result = action_07_stability.run(ctx)

    assert result.status == "success"
    # 20 fatores x 5 choques (isolado) + 5 choques (conjunto) + 1 (quebra de correlação)
    assert len(result.output["elasticidade"]) == 106
    cenarios = {r["cenario"] for r in result.output["elasticidade"]}
    assert cenarios == {"isolado", "conjunto", "quebra_correlacao"}

    by_key = {(r["cenario"], r["fator"], r["choque"]): r for r in result.output["elasticidade"]}

    # VaR = z*sigma*V — nenhuma posição referencia "wti" (§5.2 nota de design),
    # então chocá-lo não move o valor da carteira: insensibilidade correta
    # nos choques grandes (>=10%, única faixa em que a regra se aplica).
    assert by_key[("isolado", "wti", 0.10)]["flag"] == "insensivel"
    assert by_key[("isolado", "wti", 0.25)]["flag"] == "insensivel"
    assert by_key[("isolado", "wti", 0.10)]["elasticidade"] == 0.0

    # Um choque conjunto em todos os fatores move o valor da carteira de
    # forma consistente entre magnitudes — deve classificar como "ok".
    for shock in (0.001, 0.01, 0.05, 0.10, 0.25):
        assert by_key[("conjunto", "TODOS", shock)]["flag"] == "ok"

    # A grande maioria dos 106 testes deve ficar "ok" — os poucos fora disso
    # são fatores de vol (impacto pequeno na carteira, pouca opcionalidade)
    # e CPR (convexidade real via o modelo de pré-pagamento), não bugs.
    n_ok = sum(1 for r in result.output["elasticidade"] if r["flag"] == "ok")
    assert n_ok >= 85

    stored = memory.read_outputs("stability_results", "run_test")
    assert len(stored) == 106


def test_writes_one_json_file_per_test(memory, fake_llm, tmp_path, monkeypatch):
    codegen_result = _generate_real_module(memory, tmp_path, monkeypatch)
    ctx = make_ctx(memory, fake_llm, results={"06_generate_reference_code": codegen_result})

    action_07_stability.run(ctx)

    from src.pipeline.actions import _common

    test_dir = _common.REPORT_DIR / "tests" / "run_test" / "07_stability_tests"
    json_files = list(test_dir.glob("*.json"))
    assert len(json_files) == 106

    sample = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert sample["action_id"] == "07_stability_tests"
    assert sample["metric"] == "VaR"
    assert "test_code" in sample
    assert sample["test_code"]["source"]
    assert "data_used" in sample
    assert "results" in sample


def test_test_id_isolated_includes_factor_and_shock():
    test_id = action_07_stability._test_id("var", "isolado", "usdbrl", 0.05)
    assert test_id == "var__choque_usdbrl__5pct"


def test_test_id_joint_includes_shock_only():
    test_id = action_07_stability._test_id("var", "conjunto", "TODOS", 0.1)
    assert test_id == "var__choque_conjunto__10pct"


def test_test_id_correlation_break_has_no_shock():
    test_id = action_07_stability._test_id("var", "quebra_correlacao", "TODOS", None)
    assert test_id == "var__quebra_correlacao"
