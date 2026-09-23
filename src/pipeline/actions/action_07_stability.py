"""Action 07 — Testes de estabilidade (CLAUDE.md §Action 07).

Para cada módulo de métrica aceito pela Action 06: perturba cada fator de
risco em {0.1%, 1%, 5%, 10%, 25%} (isolado e conjunto), roda também o cenário
de quebra de correlação herdado da Action 04 (§Action 04 item 6), e classifica
cada resultado (ok / explosão / insensível / não-linear) contra os limites de
`config/stability_bounds.yaml`. Um JSON por teste é escrito em
`report/tests/<run_id>/07_stability_tests/` (§9.1); um resumo por
metrica×fator×choque vai para a tabela `stability_results` (usada pelo
relatório final, §9.2).
"""

from __future__ import annotations

from dataclasses import asdict

from src.pipeline.config import load_yaml
from src.pipeline.contracts import ActionResult, RunContext

from . import _common, _stability_engine as se
from ._metric_loader import load_compute_function
from ._test_json import write_test_json

ACTION_ID = "07_stability_tests"


def _load_stability_config() -> tuple[tuple[float, ...], dict]:
    config = load_yaml(_common.CONFIG_DIR / "stability_bounds.yaml")
    stability = config.get("stability", {})
    choques_pct = tuple(stability.get("choques_pct", [0.001, 0.01, 0.05, 0.10, 0.25]))
    bounds = stability.get("default_bounds", se.DEFAULT_BOUNDS)
    return choques_pct, bounds


def _render_isolated_test_source(factor_name: str, shock_pct: float) -> str:
    return (
        "from src.portfolio.base_portfolio import POSITIONS\n"
        "from src.portfolio.pricing_models import price_portfolio\n"
        "from src.portfolio.data_access import load_all_risk_factors\n\n"
        "factors = load_all_risk_factors()\n"
        "market = {name: s.iloc[-1] for name, s in factors.items()}\n"
        f"market['{factor_name}'] = market['{factor_name}'] * (1 + {shock_pct})\n"
        "shocked_value = sum(price_portfolio(POSITIONS, market).values())\n"
        "# valor_choque = compute({'value': shocked_value}, {'returns': base_returns}, params)['valor']\n"
    )


def _render_joint_test_source(shock_pct: float) -> str:
    return (
        "from src.portfolio.base_portfolio import POSITIONS\n"
        "from src.portfolio.pricing_models import price_portfolio\n"
        "from src.portfolio.data_access import load_all_risk_factors\n\n"
        "factors = load_all_risk_factors()\n"
        "market = {name: s.iloc[-1] for name, s in factors.items()}\n"
        f"market = {{k: v * (1 + {shock_pct}) for k, v in market.items()}}\n"
        "shocked_value = sum(price_portfolio(POSITIONS, market).values())\n"
        "# valor_choque = compute({'value': shocked_value}, {'returns': base_returns}, params)['valor']\n"
    )


def _render_correlation_break_source() -> str:
    return (
        "from src.portfolio.base_portfolio import POSITIONS\n"
        "from src.portfolio.pricing_models import price_portfolio\n"
        "from src.portfolio.scenario_builder import generate_correlation_break_dataset\n\n"
        "stressed = generate_correlation_break_dataset(n_obs=50)\n"
        "market = {name: s.iloc[-1] for name, s in stressed.items()}\n"
        "shocked_value = sum(price_portfolio(POSITIONS, market).values())\n"
        "# valor_choque = compute({'value': shocked_value}, {'returns': base_returns}, params)['valor']\n"
    )


def _test_id(metric_slug: str, cenario: str, fator: str, choque: float | None) -> str:
    if cenario == "isolado":
        return f"{metric_slug}__choque_{fator}__{choque * 100:g}pct"
    if cenario == "conjunto":
        return f"{metric_slug}__choque_conjunto__{choque * 100:g}pct"
    return f"{metric_slug}__quebra_correlacao"


def run(ctx: RunContext) -> ActionResult:
    codegen = ctx.results["06_generate_reference_code"]
    modules = codegen.output.get("modules", [])

    if not modules:
        return ActionResult(
            status="skipped",
            output={"elasticidade": []},
            notes=["Nenhum módulo de métrica disponível (Action 06) — testes de estabilidade não aplicáveis."],
        )

    from src.portfolio import data_access
    from src.portfolio.base_portfolio import POSITIONS
    from src.portfolio.portfolio_history import compute_portfolio_value_series
    from src.portfolio.scenario_builder import generate_correlation_break_dataset

    choques_pct, bounds = _load_stability_config()

    all_factors = data_access.load_all_risk_factors()
    base_market = {name: float(s.iloc[-1]) for name, s in all_factors.items()}
    value_series = compute_portfolio_value_series()
    base_returns = [float(v) for v in value_series.pct_change().dropna().to_list()]

    stressed_series = generate_correlation_break_dataset(n_obs=50)
    stressed_market = {name: float(s.iloc[-1]) for name, s in stressed_series.items()}

    all_results: list[dict] = []
    n_within_limit = 0
    n_total = 0

    for module in modules:
        compute = load_compute_function(module["path"], module["module_name"])
        params = module.get("params", {})
        metric_slug = module["module_name"]

        results = se.run_isolated_and_joint_tests(
            metrica=module["nome"], compute=compute, params=params, positions=POSITIONS,
            base_market=base_market, base_returns=base_returns, choques_pct=choques_pct, bounds=bounds,
        )
        results.append(
            se.run_correlation_break_test(
                metrica=module["nome"], compute=compute, params=params, positions=POSITIONS,
                base_market=base_market, base_returns=base_returns, stressed_market=stressed_market, bounds=bounds,
            )
        )

        for result in results:
            row = asdict(result)
            ctx.memory.write_output("stability_results", ctx.run_id, ACTION_ID, row)
            all_results.append(row)
            n_total += 1
            if result.dentro_do_limite:
                n_within_limit += 1

            if result.cenario == "isolado":
                source = _render_isolated_test_source(result.fator, result.choque)
                risk_factor_paths = [f"data/risk_factors/{result.fator}.csv"]
            elif result.cenario == "conjunto":
                source = _render_joint_test_source(result.choque)
                risk_factor_paths = [f"data/risk_factors/{name}.csv" for name in base_market]
            else:
                source = _render_correlation_break_source()
                risk_factor_paths = ["data/risk_factors/correlation_matrix.csv"]

            write_test_json(
                run_id=ctx.run_id, action_id=ACTION_ID,
                test_id=_test_id(metric_slug, result.cenario, result.fator, result.choque),
                metric=module["nome"], backend_llm=ctx.llm_client.backend,
                test_code_source=source, test_code_file=f"gerado dinamicamente por {ACTION_ID}",
                data_used={
                    "risk_factors": risk_factor_paths,
                    "portfolio_snapshot": "src/portfolio/base_portfolio.py:POSITIONS",
                    "scenario": result.cenario,
                    "params": {"choque_pct": result.choque, "metrica_params": params},
                },
                results=row,
                report_dir=_common.REPORT_DIR,
            )

    n_flagged = n_total - n_within_limit
    return ActionResult(
        status="success",
        output={"elasticidade": all_results},
        notes=[f"{n_total} teste(s) de estabilidade rodados em {len(modules)} métrica(s); {n_flagged} fora do limite."],
    )
