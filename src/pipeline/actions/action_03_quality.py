"""Action 03 — Avaliação da qualidade da documentação (CLAUDE.md §Action 03)."""

from __future__ import annotations

from src.pipeline.contracts import ActionResult, RunContext

from ._common import load_prompt_template

ACTION_ID = "03_assess_doc_quality"

_RUBRIC_ITEMS = (
    "escopo_de_aplicacao",
    "proposta_do_modelo",
    "desenvolvimento_metodologico",
    "declaracao_e_teste_de_hipoteses",
    "limitacoes",
    "motivacao_do_modelo",
    "codigo_exemplo_anexo",
)

_RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["itens", "nota_agregada"],
    "properties": {"itens": {"type": "array"}, "nota_agregada": {"type": "number"}},
}

_SYSTEM = (
    "Você é um validador independente de modelo de risco (MRM) avaliando qualidade documental "
    "com uma rubrica fixa. Responda sempre em JSON estrito, citando evidência ou 'ausente'."
)


def run(ctx: RunContext) -> ActionResult:
    ingest = ctx.results["01_ingest_documentation"]
    text = ingest.output.get("methodological_text", "")

    if not text.strip():
        return ActionResult(
            status="needs_human_review",
            output={"itens": [], "nota_agregada": 0.0, "gaps_priorizados": []},
            notes=["Sem texto metodológico — não há base para avaliar qualidade documental."],
        )

    template = load_prompt_template(ACTION_ID, "rubric.md")
    prompt = template.replace("{texto}", text)

    response = ctx.llm_client.complete(
        system=_SYSTEM, user=prompt, response_schema=_RESPONSE_SCHEMA, temperature=0.0
    )
    ctx.memory.log_llm_call(ctx.run_id, ACTION_ID, response)

    if response.parsed is None:
        return ActionResult(
            status="needs_human_review",
            output={"itens": [], "nota_agregada": 0.0, "gaps_priorizados": []},
            notes=["LLM não retornou JSON válido para a rubrica de qualidade documental."],
        )

    parsed = response.parsed
    scored_items = {item.get("item") for item in parsed.get("itens", [])}
    missing = [item for item in _RUBRIC_ITEMS if item not in scored_items]
    if missing:
        parsed.setdefault("itens", []).extend(
            {"item": item, "nota": 0, "evidencia": "ausente"} for item in missing
        )

    # Nunca confia na aritmética do LLM para a nota agregada — modelos pequenos
    # (§2.1, qwen3:4b) erram somas/médias com frequência. Recalcula a média a
    # partir das notas por item, que já validamos/preenchemos acima.
    llm_reported_nota = parsed.get("nota_agregada")
    itens = parsed.get("itens", [])
    notas = [item.get("nota", 0) for item in itens]
    computed_nota = round(sum(notas) / len(notas), 2) if notas else 0.0
    parsed["nota_agregada"] = computed_nota

    notes = [f"nota agregada (recalculada a partir dos itens): {computed_nota}"]
    if llm_reported_nota is not None and not _close(llm_reported_nota, computed_nota):
        notes.append(
            f"LLM reportou nota_agregada={llm_reported_nota}, divergente da média real dos itens "
            f"({computed_nota}) — usado o valor recalculado."
        )

    ctx.memory.write_output("quality_scores", ctx.run_id, ACTION_ID, parsed)

    return ActionResult(status="success", output=parsed, notes=notes)


def _close(a: float, b: float, tol: float = 0.05) -> bool:
    return abs(a - b) <= tol
