"""Action 05 — Aderência normativa, condicional (CLAUDE.md §Action 05)."""

from __future__ import annotations

import json

from src.pipeline.contracts import ActionResult, RunContext

ACTION_ID = "05_regulatory_adherence"

_RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["clausulas"],
    "properties": {"clausulas": {"type": "array"}},
}

_SYSTEM = (
    "Você é um validador independente de modelos de risco checando aderência normativa. "
    "Compare cláusula a cláusula, sem inventar conteúdo da norma. Responda em JSON estrito."
)


def run(ctx: RunContext) -> ActionResult:
    extraction = ctx.results["02_extract_model_spec"]
    metrics = extraction.output.get("metrics", [])
    is_regulatory = any(m.get("tipo") == "padronizado_regulatorio" for m in metrics)
    norm_text = ctx.inputs.get("norm_text")

    if not is_regulatory:
        return ActionResult(
            status="skipped",
            output={"motivo": "modelo nao regulamentado"},
            notes=["Nenhuma métrica extraída foi classificada como padronizado/regulatório."],
        )

    if not norm_text:
        return ActionResult(
            status="skipped",
            output={"motivo": "norma nao disponibilizada"},
            notes=["Modelo é regulatório, mas o texto da norma não foi anexado — anexe-o para habilitar a Action 05."],
        )

    prompt = (
        "ESPECIFICAÇÃO EXTRAÍDA DO MODELO (JSON):\n---\n"
        f"{json.dumps(extraction.output, ensure_ascii=False)}\n---\n\n"
        "TEXTO DA NORMA:\n---\n"
        f"{norm_text}\n---\n\n"
        "Para cada cláusula relevante da norma, produza um item JSON com: "
        '"clausula", "requisito", "tratamento_na_doc", "aderente" (true/false/"parcial"), "observacao". '
        'Responda em JSON estrito: {"clausulas": [...]}'
    )

    response = ctx.llm_client.complete(system=_SYSTEM, user=prompt, response_schema=_RESPONSE_SCHEMA, temperature=0.0)
    ctx.memory.log_llm_call(ctx.run_id, ACTION_ID, response)

    if response.parsed is None:
        return ActionResult(
            status="needs_human_review",
            output={"clausulas": []},
            notes=["LLM não retornou JSON válido para a matriz de aderência normativa."],
        )

    ctx.memory.write_output("regulatory_adherence", ctx.run_id, ACTION_ID, response.parsed)
    return ActionResult(
        status="success",
        output=response.parsed,
        notes=[f"{len(response.parsed.get('clausulas', []))} cláusula(s) avaliada(s)."],
    )
