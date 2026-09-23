"""Teste extensível: concentração por fator de risco (CLAUDE.md §Action 09).

Reaproveita os resultados já calculados pela Action 07 (não recalcula nada):
mede, para cada fator, a participação de |delta_metrica| no choque isolado de
referência (1%) sobre a soma de |delta_metrica| de todos os fatores — uma
proxy de "quanto da sensibilidade total da métrica vem de um único fator".
Um fator respondendo por uma fração grande demais da sensibilidade total é
concentração de risco, mesmo que a carteira tenha 26 posições nominalmente
diversificadas.
"""

from __future__ import annotations

from src.pipeline.contracts import ActionResult, RunContext

TEST_ID = "concentration_test"
REFERENCE_SHOCK = 0.01
CONCENTRATION_THRESHOLD = 0.40  # convenção documentada: >40% da sensibilidade total num único fator


def run(ctx: RunContext) -> ActionResult:
    stability = ctx.results.get("07_stability_tests")
    if stability is None or not stability.output.get("elasticidade"):
        return ActionResult(
            status="skipped",
            output={"concentracao": []},
            notes=["Sem resultados de estabilidade (Action 07) — concentração não calculável nesta run."],
        )

    isolated = [
        r for r in stability.output["elasticidade"]
        if r.get("cenario") == "isolado" and r.get("choque") == REFERENCE_SHOCK
    ]
    if not isolated:
        return ActionResult(
            status="skipped",
            output={"concentracao": []},
            notes=[f"Nenhum resultado isolado no choque de referência ({REFERENCE_SHOCK:g}) — concentração não calculável."],
        )

    total_abs_delta = sum(abs(r["delta_metrica"]) for r in isolated)

    concentracao = []
    for r in isolated:
        share = abs(r["delta_metrica"]) / total_abs_delta if total_abs_delta > 0 else 0.0
        concentracao.append({"metrica": r["metrica"], "fator": r["fator"], "share_concentracao": share})
    concentracao.sort(key=lambda c: -c["share_concentracao"])

    fatores_concentrados = [c for c in concentracao if c["share_concentracao"] > CONCENTRATION_THRESHOLD]

    notes = [f"{len(fatores_concentrados)} fator(es) acima do limiar de concentração ({CONCENTRATION_THRESHOLD:.0%})."]
    if fatores_concentrados:
        notes.append(
            "Concentrados: " + ", ".join(f"{c['fator']} ({c['share_concentracao']:.1%})" for c in fatores_concentrados)
        )

    return ActionResult(
        status="success",
        output={"concentracao": concentracao, "fatores_concentrados": fatores_concentrados, "limiar": CONCENTRATION_THRESHOLD},
        notes=notes,
    )
