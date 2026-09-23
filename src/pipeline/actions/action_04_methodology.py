"""Action 04 — Avaliação da qualidade metodológica (CLAUDE.md §Action 04).

Parte qualitativa (levantar hipóteses, classificar testabilidade, comparar com
metodologia desafiante, checar referências) via LLM. Parte quantitativa
(normalidade, autocorrelação/i.i.d., estacionariedade aproximada — §2.1 item
2) roda contra os históricos sintéticos congelados (§5.3), lidos só-leitura
via `src.portfolio.data_access`.

O item 6 do §Action 04 ("recalcular a métrica sob quebra de correlação e
comparar com o caso base") não roda aqui: ele exige o código de referência da
Action 06, que roda DEPOIS de 04 no pipeline (§3.4) — por isso o próprio
CLAUDE.md diz que esse teste "alimenta também a Action 07/08", não a 04. Esta
action só prepara o terreno (a matriz de correlação estressada já existe em
`scenario_builder.stressed_correlation_matrix`); a Action 07 é quem de fato
recalcula e compara.
"""

from __future__ import annotations

import json

from src.pipeline.contracts import ActionResult, RunContext

from ._common import load_prompt_template

ACTION_ID = "04_assess_methodology"

# Cesta fixa de fatores usada para testar hipóteses declaradas na doc (§2.1
# item 2). Simplificação deliberada: mapear o escopo declarado por métrica
# (produtos/moedas) para um subconjunto de fatores exigiria heurísticas de
# texto frágeis; testar sempre a mesma cesta representativa (uma curva de
# juros, um câmbio, uma ação) é mais robusto e é logado como decisão a cada
# run que efetivamente rodar testes quantitativos.
DEFAULT_TEST_FACTORS: tuple[tuple[str, str], ...] = (("di_pre", "rate"), ("usdbrl", "price"), ("ibov", "price"))

_RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["hipoteses_avaliadas", "comparacao_metodologia_desafiante", "limitacoes_discutidas", "referencias_citadas"],
    "properties": {
        "hipoteses_avaliadas": {"type": "array"},
        "limitacoes_discutidas": {"type": "array"},
        "referencias_citadas": {"type": "array"},
    },
}

_SYSTEM = (
    "Você é um validador independente de modelos quantitativos de risco, ancorado em referências "
    "técnicas reais. Nunca invente número de norma, página ou citação textual — na dúvida, "
    "referencie de forma genérica e marque referencia_nao_verificada: true. Responda em JSON estrito."
)


def _classify_hypothesis(text: str) -> set[str]:
    t = text.lower()
    matched = set()
    if "normal" in t:
        matched.add("normalidade")
    if "i.i.d" in t or "iid" in t or "independ" in t or "autocorrela" in t:
        matched.add("iid")
    if "estacion" in t or "stationary" in t:
        matched.add("estacionariedade")
    return matched


def _extract_hypothesis_texts(hipoteses) -> list[str]:
    """Extrai textos de hipótese de forma defensiva. O schema pedido à Action 02
    é `{"explicitas": [...], "implicitas": [...]}`, mas um modelo pequeno nem
    sempre segue a forma exata mesmo com JSON estrito pedido e validado no
    top-level (§2.1) — na prática já foi observado retornar uma LISTA de
    objetos `{"explicita": ..., "implicita": ...}` em vez do dict esperado.
    Nunca confiar cegamente na forma; aceitar as variações plausíveis e não
    quebrar (AttributeError) nas demais."""
    texts: list[str] = []
    if isinstance(hipoteses, dict):
        for key in ("explicitas", "implicitas"):
            value = hipoteses.get(key, [])
            if isinstance(value, list):
                texts.extend(str(v) for v in value if v)
            elif value:
                texts.append(str(value))
    elif isinstance(hipoteses, list):
        for item in hipoteses:
            if isinstance(item, dict):
                for key in ("explicita", "implicita", "explicitas", "implicitas"):
                    if item.get(key):
                        texts.append(str(item[key]))
            elif item:
                texts.append(str(item))
    return texts


def _collect_hypothesis_texts(metrics: list[dict]) -> list[str]:
    texts = []
    for metric in metrics:
        texts.extend(_extract_hypothesis_texts(metric.get("hipoteses", {})))
    return texts


def _run_quantitative_tests(ctx: RunContext, test_types: set[str]) -> dict:
    from src.portfolio import data_access, hypothesis_tests as ht

    results: dict[str, dict] = {}
    for test_type in sorted(test_types):
        per_factor = {}
        for factor_name, kind in DEFAULT_TEST_FACTORS:
            series = data_access.load_risk_factor(factor_name)
            changes = ht.factor_changes(series, kind)
            if test_type == "normalidade":
                per_factor[factor_name] = ht.normality_test(changes)
            elif test_type == "iid":
                per_factor[factor_name] = ht.autocorrelation_test(changes)
            elif test_type == "estacionariedade":
                per_factor[factor_name] = ht.stationarity_test(changes)
        results[test_type] = per_factor

    ctx.memory.log_decision(
        run_id=ctx.run_id,
        action_id=ACTION_ID,
        campo_afetado="fatores_de_teste_hipotese",
        ambiguidade_encontrada="A documentação não permite mapear de forma confiável quais fatores de "
        "risco específicos correspondem às hipóteses declaradas (ex.: 'retornos da carteira').",
        decisao_tomada=f"Testes quantitativos rodados contra uma cesta fixa representativa: "
        f"{', '.join(name for name, _ in DEFAULT_TEST_FACTORS)}.",
        justificativa="Mapear o escopo textual declarado para fatores específicos exigiria heurísticas "
        "de NLP frágeis; uma cesta fixa e documentada é mais robusta e reproduzível.",
        fonte_da_decisao="assunção conservadora",
        criticidade="media",
    )
    return results


def run(ctx: RunContext) -> ActionResult:
    extraction = ctx.results["02_extract_model_spec"]
    metrics = extraction.output.get("metrics", [])

    if not metrics:
        return ActionResult(
            status="needs_human_review",
            output={"hipoteses_avaliadas": [], "referencias_citadas": []},
            notes=["Nenhuma métrica extraída (Action 02) — nada a avaliar metodologicamente."],
        )

    template = load_prompt_template(ACTION_ID, "methodology.md")
    prompt = template.replace("{extracao}", json.dumps(extraction.output, ensure_ascii=False))

    response = ctx.llm_client.complete(
        system=_SYSTEM, user=prompt, response_schema=_RESPONSE_SCHEMA, temperature=0.0
    )
    ctx.memory.log_llm_call(ctx.run_id, ACTION_ID, response)

    if response.parsed is None:
        return ActionResult(
            status="needs_human_review",
            output={"hipoteses_avaliadas": [], "referencias_citadas": []},
            notes=["LLM não retornou JSON válido para a avaliação metodológica qualitativa."],
        )

    parsed = response.parsed
    notes = []

    hypothesis_texts = _collect_hypothesis_texts(metrics)
    test_types_needed: set[str] = set()
    for text in hypothesis_texts:
        test_types_needed |= _classify_hypothesis(text)

    if test_types_needed:
        quantitative_results = _run_quantitative_tests(ctx, test_types_needed)
        parsed["testes_quantitativos"] = quantitative_results
        for test_type, per_factor in quantitative_results.items():
            reject_key = {
                "normalidade": "rejects_normality",
                "iid": "rejects_iid",
                "estacionariedade": "rejects_stationarity",
            }[test_type]
            n_rejected = sum(1 for r in per_factor.values() if r[reject_key])
            notes.append(f"{test_type}: rejeitada em {n_rejected}/{len(per_factor)} fator(es) da cesta de teste.")
    else:
        parsed["testes_quantitativos"] = {}
        notes.append(
            "Nenhuma hipótese declarada mapeou para um teste quantitativo implementado "
            "(normalidade/i.i.d./estacionariedade) — nenhum teste rodado nesta run."
        )

    for ref in parsed.get("referencias_citadas", []):
        if ref.get("referencia_nao_verificada"):
            notes.append(f"referência não verificada: {ref.get('referencia')}")

    ctx.memory.write_output("methodology_assessment", ctx.run_id, ACTION_ID, parsed)

    return ActionResult(status="success", output=parsed, notes=notes)
