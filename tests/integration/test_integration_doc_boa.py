"""Teste de integração fim-a-fim (CLAUDE.md §3.3) — fixture `doc_boa` (SA-CCR).

Roda o pipeline completo (Actions 01→10) contra uma documentação bem escrita
e verifica os critérios de aceite de §3.3: pipeline não cai em
needs_human_review por falta de informação, nota de qualidade agregada alta,
poucas decisões de criticidade alta, código de referência gerado e aceito, e
estabilidade sem explosão numérica.

Só roda com LLM_BACKEND=ollama setado explicitamente E um Ollama alcançável
— fica pulado (skip), não falho, em qualquer outro ambiente (§3.3: "rodados
em CI com LLM_BACKEND=ollama"; a suíte rápida de unit/action tests não deve
depender de um LLM vivo).
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

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "doc_boa"


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


def test_doc_boa_saccr_end_to_end(tmp_path, monkeypatch):
    from src.pipeline.actions import _common, action_06_codegen, action_10_report

    monkeypatch.setattr(action_10_report, "REPORT_DIR", tmp_path / "report")
    monkeypatch.setattr(action_06_codegen, "METRICS_DIR", tmp_path / "metrics")
    monkeypatch.setattr(_common, "REPORT_DIR", tmp_path / "report")

    memory = MemoryStore(tmp_path / "state.db")
    llm_client = get_llm_client("ollama")

    doc_paths = [
        str(FIXTURE_DIR / "saccr_metodologia.md"),
        str(FIXTURE_DIR / "exemplo_calculado.csv"),
    ]
    results = run_pipeline(run_id="doc_boa", memory=memory, llm_client=llm_client, inputs={"doc_paths": doc_paths})

    # (a) pipeline não deve cair em needs_human_review por FALTA DE INFORMAÇÃO
    # nas actions 01-05 (a doc é completa: escopo, fórmulas, hipóteses,
    # limitações, motivação e exemplo anexado estão todos presentes).
    for action_id in ("01_ingest_documentation", "02_extract_model_spec", "03_assess_doc_quality", "04_assess_methodology"):
        assert results[action_id].status in ("success", "skipped"), (
            f"{action_id} caiu em '{results[action_id].status}' — notas: {results[action_id].notes}"
        )

    # (b) nota de qualidade documental agregada alta (>= 3.0/4, §3.3)
    quality_rows = memory.read_outputs("quality_scores", "doc_boa")
    assert quality_rows, "Action 03 não produziu score de qualidade"
    nota_agregada = quality_rows[-1]["data"]["nota_agregada"]
    assert nota_agregada >= 3.0, f"nota agregada {nota_agregada} abaixo do esperado para doc_boa"

    # (c) decisions_log deve ter POUCAS entradas de criticidade alta
    decisions_alta = memory.get_decisions("doc_boa", criticidade="alta")
    assert len(decisions_alta) <= 3, f"decisions_log com {len(decisions_alta)} entradas de criticidade alta: {decisions_alta}"

    # (d) código de referência gerado e aceito em sandbox (Add-On do SA-CCR)
    codegen_result = results["06_generate_reference_code"]
    assert codegen_result.status == "success", f"Action 06 não gerou código aceito: {codegen_result.notes}"
    assert len(codegen_result.output["modules"]) >= 1

    # (e) testes de estabilidade rodaram e não sinalizam EXPLOSÃO numérica
    # (insensibilidade/não-linearidade em fatores irrelevantes ao netting set
    # — ex. vol de commodity para uma carteira só de juros/câmbio — é
    # comportamento correto, não uma falha; só explosão indica instabilidade
    # numérica de verdade, §Action07).
    stability_result = results["07_stability_tests"]
    assert stability_result.status == "success", f"Action 07 não rodou: {stability_result.notes}"
    explosions = [r for r in stability_result.output["elasticidade"] if r["flag"] == "explosao"]
    assert explosions == [], f"{len(explosions)} teste(s) de estabilidade sinalizaram explosão numérica: {explosions[:3]}"

    # (f) relatório final foi escrito
    report_result = results["10_replicability_report"]
    assert report_result.status == "success"
    report_path = Path(report_result.output["report_path"])
    assert report_path.exists()

    memory.close()
