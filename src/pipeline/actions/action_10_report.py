"""Action 10 — Replicabilidade (CLAUDE.md §Action 10 / §9.2).

Consolida decisions_log + saídas das actions anteriores e materializa
`report/final_report_<run_id>.md` programaticamente a partir de `memory/state.db`
(nunca escrito "à mão"). Roda até o fim mesmo com lacunas grandes — o relatório
em si é onde a fidedignidade baixa (se houver) é reportada com clareza.
"""

from __future__ import annotations

from pathlib import Path

from src.pipeline.contracts import ActionResult, RunContext
from src.pipeline.report_render import render_markdown

from . import _charts
from ._common import REPORT_DIR

ACTION_ID = "10_replicability_report"


def _generate_charts(ctx: RunContext) -> dict[str, str]:
    """Gera os gráficos exigidos por §9.2 a partir das tabelas já persistidas
    (nunca recalcula nada) e devolve `{nome_logico: caminho_relativo_ao_.md}`
    para embutir no Markdown — vazio quando não há dado suficiente para um
    gráfico (ex.: Action 07/08 não rodaram nesta run)."""
    assets_dir = REPORT_DIR / "assets"
    stability_rows = [row["data"] for row in ctx.memory.read_outputs("stability_results", ctx.run_id)]
    backtest_rows = [row["data"] for row in ctx.memory.read_outputs("backtest_results", ctx.run_id)]

    refs: dict[str, str] = {}
    stability_chart = _charts.write_stability_elasticity_chart(assets_dir, ctx.run_id, stability_rows)
    if stability_chart is not None:
        refs["stability_elasticity"] = f"assets/{ctx.run_id}/{stability_chart.name}"

    backtest_chart = _charts.write_backtest_exceptions_chart(assets_dir, ctx.run_id, backtest_rows)
    if backtest_chart is not None:
        refs["backtest_exceptions"] = f"assets/{ctx.run_id}/{backtest_chart.name}"

    return refs


def run(ctx: RunContext) -> ActionResult:
    decisions = ctx.memory.get_decisions(ctx.run_id)
    alta = [d for d in decisions if d["criticidade"] == "alta"]

    asset_refs = _generate_charts(ctx)

    report_path = REPORT_DIR / f"final_report_{ctx.run_id}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    markdown = render_markdown(ctx.memory, ctx.run_id, asset_refs=asset_refs)
    report_path.write_text(markdown, encoding="utf-8")

    artifacts = [report_path] + [REPORT_DIR / rel for rel in asset_refs.values()]
    notes = [
        f"{len(decisions)} decisão(ões) em decisions_log ({len(alta)} de criticidade alta).",
        f"Relatório final escrito em {report_path}.",
        f"{len(asset_refs)} gráfico(s) gerado(s) em {REPORT_DIR / 'assets' / ctx.run_id}.",
    ]
    return ActionResult(
        status="success",
        output={
            "decisions_total": len(decisions),
            "decisions_alta": len(alta),
            "report_path": str(report_path),
            "asset_paths": {k: str(REPORT_DIR / v) for k, v in asset_refs.items()},
        },
        artifacts=artifacts,
        notes=notes,
    )
