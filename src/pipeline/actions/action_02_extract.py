"""Action 02 — Extração da especificação do modelo (CLAUDE.md §Action 02)."""

from __future__ import annotations

from src.pipeline.contracts import ActionResult, RunContext

from ._common import load_prompt_template

ACTION_ID = "02_extract_model_spec"

_RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["metrics"],
    "properties": {"metrics": {"type": "array"}},
}

_SYSTEM = (
    "Você é um extrator estruturado de especificações de modelos quantitativos de risco. "
    "Responda sempre em JSON estrito, nunca invente conteúdo que não esteja no texto fornecido."
)


def run(ctx: RunContext) -> ActionResult:
    ingest = ctx.results["01_ingest_documentation"]
    text = ingest.output.get("methodological_text", "")

    if not text.strip():
        return ActionResult(
            status="needs_human_review",
            output={"metrics": []},
            notes=["Sem texto metodológico (Action 01) — nada a extrair."],
        )

    template = load_prompt_template(ACTION_ID, "extract.md")
    prompt = template.replace("{texto}", text)

    response = ctx.llm_client.complete(
        system=_SYSTEM, user=prompt, response_schema=_RESPONSE_SCHEMA, temperature=0.0
    )
    ctx.memory.log_llm_call(ctx.run_id, ACTION_ID, response)

    if response.parsed is None:
        ctx.memory.log_decision(
            run_id=ctx.run_id,
            action_id=ACTION_ID,
            campo_afetado="extracao_geral",
            ambiguidade_encontrada="O LLM não retornou JSON válido conforme o schema esperado, mesmo após repair prompt.",
            decisao_tomada="Extração marcada como needs_human_review; pipeline segue com metrics=[].",
            justificativa="Regra §2.1: nunca travar o pipeline por causa de um passo de LLM.",
            fonte_da_decisao="assunção conservadora",
            criticidade="alta",
        )
        return ActionResult(
            status="needs_human_review",
            output={"metrics": []},
            notes=["LLM não retornou JSON válido para a especificação do modelo."],
        )

    metrics = response.parsed.get("metrics", [])
    for metric in metrics:
        nome = metric.get("nome", "metrica_sem_nome")
        for param in metric.get("parametros", []):
            if not param.get("valor_definido", False):
                ctx.memory.log_decision(
                    run_id=ctx.run_id,
                    action_id=ACTION_ID,
                    campo_afetado=f"{nome}.parametro.{param.get('nome', '?')}",
                    ambiguidade_encontrada=f"Parâmetro '{param.get('nome', '?')}' da métrica '{nome}' não tem valor definido no texto.",
                    decisao_tomada="Decisão de implementação será tomada na Action 06 e logada lá.",
                    justificativa="Regra §Action 02: toda lacuna já é logada aqui com criticidade provisória.",
                    fonte_da_decisao="assunção conservadora",
                    criticidade="media",
                )

    ctx.memory.write_output("extractions", ctx.run_id, ACTION_ID, response.parsed)

    return ActionResult(
        status="success",
        output=response.parsed,
        notes=[f"{len(metrics)} métrica(s) extraída(s)."],
    )
