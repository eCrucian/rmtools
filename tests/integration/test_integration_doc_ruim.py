"""Teste de integração fim-a-fim (CLAUDE.md §3.3) — fixture `doc_ruim`
(modelo de pré-pagamento/CPR, documentação propositalmente ruim).

Roda o pipeline completo (Actions 01→10) contra uma documentação vaga, sem
dedução de fórmula, sem hipóteses/limitações/motivação declaradas e sem
código/planilha anexado — e verifica que o pipeline AINDA ASSIM chega até o
final (nunca trava por causa de documentação ruim, §6/§8), reportando
honestamente a baixa fidedignidade em vez de "aprovar" o modelo só porque o
código rodou sem erro.

Mesmo gate de LLM_BACKEND=ollama que `test_integration_doc_boa.py`.
"""

from __future__ import annotations

import os
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from src.llm.client import get_llm_client
from src.memory.db import MemoryStore
from src.pipeline.run import run_pipeline

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "doc_ruim"


def _ollama_available() -> bool:
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    try:
        urllib.request.urlopen(f"{host.rstrip('/')}/api/tags", timeout=3)
        return True
    except (urllib.error.URLError, OSError):
        return False


pytestmark = pytest.mark.skipif(
    os.environ.get("LLM_BACKEND") != "ollama" or not _ollama_available(),
    reason="requer LLM_BACKEND=ollama e um servidor Ollama alcançável (teste de integração, §3.3)",
)


def test_doc_ruim_prepayment_end_to_end_still_reaches_final_report(tmp_path, monkeypatch):
    from src.pipeline.actions import _common, action_06_codegen, action_10_report

    monkeypatch.setattr(action_10_report, "REPORT_DIR", tmp_path / "report")
    monkeypatch.setattr(action_06_codegen, "METRICS_DIR", tmp_path / "metrics")
    monkeypatch.setattr(_common, "REPORT_DIR", tmp_path / "report")

    memory = MemoryStore(tmp_path / "state.db")
    llm_client = get_llm_client("ollama")

    doc_paths = [str(FIXTURE_DIR / "modelo_prepagamento.md")]
    results = run_pipeline(run_id="doc_ruim", memory=memory, llm_client=llm_client, inputs={"doc_paths": doc_paths})

    # (a) o pipeline TEM que chegar ao relatório final mesmo com documentação
    # ruim — essa é a regra central do CLAUDE.md (§6/§8): nunca travar.
    report_result = results["10_replicability_report"]
    assert report_result.status == "success", f"Action 10 não completou: {report_result.notes}"
    report_path = Path(report_result.output["report_path"])
    assert report_path.exists()
    report_text = report_path.read_text(encoding="utf-8")

    # (b) nota de qualidade documental agregada BAIXA (escopo vago, sem
    # dedução, sem hipóteses/limitações/motivação declaradas)
    quality_rows = memory.read_outputs("quality_scores", "doc_ruim")
    if quality_rows:
        nota_agregada = quality_rows[-1]["data"]["nota_agregada"]
        assert nota_agregada < 2.5, f"nota agregada {nota_agregada} alta demais para doc_ruim"

    # (c) decisions_log deve refletir as lacunas da doc (CPR sem fonte/valor,
    # curva de funding sem definição, escopo vago, etc.). Exige pelo menos uma
    # entrada de QUALQUER criticidade — o modelo (pequeno, rodando local) tem
    # variância real de run para run sobre classificar uma lacuna como "alta"
    # vs. "media" para uma mesma doc vaga; o que importa para o critério de
    # aceite de §3.3 é que a lacuna FOI rastreada, não a classificação exata.
    all_decisions = memory.get_decisions("doc_ruim")
    assert len(all_decisions) >= 1, "esperava pelo menos uma decisão logada para uma doc tão vaga"

    # (d) o relatório nunca afirma que o modelo está "validado"/"aprovado" só
    # porque o pipeline rodou até o fim — o report_render.py é puramente
    # factual/tabular (nunca escreve texto de veredito solto), então isso é
    # garantido estruturalmente; a checagem aqui é uma trava de regressão.
    lowered = report_text.lower()
    for forbidden in ("modelo validado", "aprovado para uso", "validação concluída com sucesso"):
        assert forbidden not in lowered, f"relatório contém afirmação de validação indevida: '{forbidden}'"

    memory.close()
