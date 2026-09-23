"""Action 08 — Backtesting/performance (CLAUDE.md §Action 08).

Para cada módulo de métrica aceito pela Action 06: recalcula o VaR de 1 dia
em janela móvel de 250 dias contra o histórico congelado da carteira base, e
roda Kupiec/Christoffersen/semáforo de Basileia por holding period
{1,10,30,60,90,180} — cada holding period escala o VaR por √h (convenção de
mercado, decisão logada) e compara contra o P&L realizado em janelas
SOBREPOSTAS de h dias (única forma de ter amostra suficiente com 1000 dias de
histórico; viola i.i.d., reportado como limitação, não escondido). Um JSON
por teste×holding_period é escrito em `report/tests/<run_id>/08_backtesting/`
(§9.1); um resumo vai para a tabela `backtest_results` (§9.2).
"""

from __future__ import annotations

from dataclasses import replace

from src.pipeline.config import load_yaml
from src.pipeline.contracts import ActionResult, RunContext

from . import _backtest_engine as be
from . import _common
from ._metric_loader import load_compute_function
from ._test_json import write_test_json

ACTION_ID = "08_backtesting"

_CONFIDENCE_KEYWORDS = ("confian", "confidence")


def _load_backtest_config() -> tuple[int, tuple[int, ...]]:
    config = load_yaml(_common.CONFIG_DIR / "stability_bounds.yaml")
    backtest = config.get("backtest", {})
    janela_minima = int(backtest.get("janela_minima_dias_uteis", be.MIN_HISTORY_DAYS))
    holding_periods = tuple(int(h) for h in backtest.get("holding_periods", [1, 10, 30, 60, 90, 180]))
    return janela_minima, holding_periods


def _extract_confidence(ctx: RunContext, metric_nome: str, params: dict) -> float:
    for key, value in params.items():
        if any(kw in key.lower() for kw in _CONFIDENCE_KEYWORDS) and isinstance(value, (int, float)):
            return float(value)

    ctx.memory.log_decision(
        run_id=ctx.run_id, action_id=ACTION_ID,
        campo_afetado=f"{metric_nome}.backtest.nivel_confianca",
        ambiguidade_encontrada="Não foi possível identificar um parâmetro de nível de confiança "
        "numérico nos parâmetros resolvidos da métrica para calibrar Kupiec/semáforo.",
        decisao_tomada=f"Assumido nível de confiança default de {be.DEFAULT_CONFIDENCE} para o backtest.",
        justificativa="Convenção de mercado usual para VaR regulatório/interno.",
        fonte_da_decisao="convenção de mercado", criticidade="media",
    )
    return be.DEFAULT_CONFIDENCE


def _render_test_source(holding_period: int, rolling_window: int) -> str:
    return (
        "from src.portfolio.portfolio_history import (\n"
        "    compute_portfolio_value_series, compute_portfolio_input_series,\n"
        ")\n"
        "import numpy as np, math\n\n"
        "value_series = compute_portfolio_value_series().to_numpy()\n"
        "portfolio_inputs = compute_portfolio_input_series()  # {'value':..., 'positions':[...]}\n"
        f"rolling_window = {rolling_window}\n"
        f"holding_period = {holding_period}\n"
        "returns = np.diff(value_series) / value_series[:-1]\n"
        "for t in range(rolling_window, len(value_series)):\n"
        "    window_returns = returns[t-rolling_window:t].tolist()\n"
        "    var_1day = compute(portfolio_inputs[t], {'returns': window_returns}, params)['valor']\n"
        "    var_h = var_1day * math.sqrt(holding_period)\n"
        "    # realized_loss = -(value_series[t+holding_period] - value_series[t]); exceção se > var_h\n"
    )


def run(ctx: RunContext) -> ActionResult:
    codegen = ctx.results["06_generate_reference_code"]
    modules = codegen.output.get("modules", [])

    if not modules:
        return ActionResult(
            status="skipped",
            output={"holding_periods": []},
            notes=["Nenhum módulo de métrica disponível (Action 06) — backtesting não aplicável."],
        )

    from src.portfolio.portfolio_history import compute_portfolio_input_series, compute_portfolio_value_series

    janela_minima, holding_periods = _load_backtest_config()
    value_series = compute_portfolio_value_series()

    if len(value_series) < janela_minima:
        return ActionResult(
            status="needs_human_review",
            output={"holding_periods": []},
            notes=[
                f"Histórico disponível ({len(value_series)} dias) é menor que a janela mínima "
                f"obrigatória de {janela_minima} dias úteis (§Action 08) — backtest não confiável, não rodado.",
            ],
        )

    portfolio_inputs = compute_portfolio_input_series()

    ctx.memory.log_decision(
        run_id=ctx.run_id, action_id=ACTION_ID,
        campo_afetado="backtest.overlapping_windows",
        ambiguidade_encontrada="Com 1000 dias de histórico, holding periods longos (ex.: 180 dias) não "
        "têm amostra suficiente de janelas NÃO sobrepostas para um backtest estatisticamente robusto.",
        decisao_tomada="Usadas janelas sobrepostas (overlapping) de h dias para o P&L realizado em todo holding period.",
        justificativa="Overlapping windows violam a hipótese i.i.d. assumida por Kupiec/Christoffersen — "
        "isso é uma limitação conhecida, reportada explicitamente no relatório, não escondida.",
        fonte_da_decisao="convenção de mercado", criticidade="media",
    )

    all_results: list[dict] = []
    modules_needing_review = []

    for module in modules:
        compute = load_compute_function(module["path"], module["module_name"])
        params = module.get("params", {})
        metric_slug = module["module_name"]
        confidence = _extract_confidence(ctx, module["nome"], params)

        ctx.memory.log_decision(
            run_id=ctx.run_id, action_id=ACTION_ID,
            campo_afetado=f"{module['nome']}.escalonamento_holding_period",
            ambiguidade_encontrada="A especificação extraída (Action 02) não indica uma regra de "
            "escalonamento do VaR para holding periods diferentes de 1 dia.",
            decisao_tomada="Aplicada a convenção de raiz do tempo: VaR_h = VaR_1dia * sqrt(h).",
            justificativa="Convenção de mercado padrão (ex.: Jorion) na ausência de regra explícita na doc.",
            fonte_da_decisao="convenção de mercado", criticidade="media",
        )

        try:
            indices, var_1day = be.compute_rolling_var_1day(
                compute, params, value_series.to_numpy(), be.DEFAULT_ROLLING_WINDOW, portfolio_inputs=portfolio_inputs
            )
        except (ValueError, KeyError, TypeError) as exc:
            # KeyError/TypeError: compute() gerado pela Action 06 não é compatível com o
            # formato de portfolio fornecido (ex.: espera um campo que não existe no
            # snapshot) — falha técnica, não trava o pipeline (§6/§8), só esta métrica.
            modules_needing_review.append(module["nome"])
            ctx.memory.log_decision(
                run_id=ctx.run_id, action_id=ACTION_ID,
                campo_afetado=f"{module['nome']}.backtest",
                ambiguidade_encontrada="N/A — falha técnica ao rodar a janela móvel de VaR.",
                decisao_tomada=f"Backtest desta métrica pulado: {exc!r}",
                justificativa="bug_do_agente ou dado insuficiente — não é lacuna de documentação.",
                fonte_da_decisao="assunção conservadora", criticidade="media",
            )
            continue

        for holding_period in holding_periods:
            try:
                result = be.backtest_for_holding_period(
                    value_series.to_numpy(), indices, var_1day, holding_period, confidence
                )
            except ValueError:
                continue

            row = {"metrica": module["nome"], **result}
            ctx.memory.write_output("backtest_results", ctx.run_id, ACTION_ID, row)
            all_results.append(row)

            write_test_json(
                run_id=ctx.run_id, action_id=ACTION_ID,
                test_id=f"{metric_slug}__backtest_h{holding_period}d",
                metric=module["nome"], backend_llm=ctx.llm_client.backend,
                test_code_source=_render_test_source(holding_period, be.DEFAULT_ROLLING_WINDOW),
                test_code_file=f"gerado dinamicamente por {ACTION_ID}",
                data_used={
                    "portfolio_snapshot": "src/portfolio/base_portfolio.py:POSITIONS",
                    "holding_period": holding_period,
                    "rolling_window": be.DEFAULT_ROLLING_WINDOW,
                    "confidence": confidence,
                    "overlapping_windows": True,
                },
                results=row,
                report_dir=_common.REPORT_DIR,
            )

    status = "needs_human_review" if modules_needing_review else "success"
    notes = [f"{len(all_results)} combinação(ões) métrica×holding_period rodadas."]
    if modules_needing_review:
        notes.append("Pendentes: " + ", ".join(modules_needing_review))

    return ActionResult(status=status, output={"holding_periods": all_results}, notes=notes)
