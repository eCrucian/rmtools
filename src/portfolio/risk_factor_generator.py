"""Gerador dos 1000 dias de histórico sintético dos fatores de risco (CLAUDE.md
§5.3). **Script de geração única.** Roda-se manualmente uma vez:

    python -m src.portfolio.risk_factor_generator --freeze

O output vai para `data/risk_factors/*.csv` (um arquivo por fator + a matriz
de correlação) e, a partir daí, é tratado como fixture somente-leitura — o
pipeline (Actions 01-10) nunca importa este módulo como gerador em tempo de
execução (regra dura de §5.3/§6.8). Reexecutar este script sobrescreve os
CSVs deliberadamente; isso só deve acontecer por decisão explícita e
versionada (novo commit), nunca como efeito colateral de rodar uma validação.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from . import factors as f

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data" / "risk_factors"
START_DATE = "2021-01-04"  # âncora arbitrária e fixa — só define os rótulos de data


def _simulate_vasicek(params: f.VasicekParams, z_col: np.ndarray, dt: float) -> np.ndarray:
    n = len(z_col)
    path = np.empty(n + 1)
    path[0] = params.r0
    for t in range(n):
        drift = params.kappa * (params.theta - path[t]) * dt
        diffusion = params.sigma * np.sqrt(dt) * z_col[t]
        path[t + 1] = max(path[t] + drift + diffusion, params.floor)
    return path[1:]


def _simulate_gbm(params: f.GBMParams, z_col: np.ndarray, dt: float) -> np.ndarray:
    n = len(z_col)
    path = np.empty(n + 1)
    path[0] = params.s0
    drift = (params.mu - 0.5 * params.sigma**2) * dt
    vol_term = params.sigma * np.sqrt(dt)
    for t in range(n):
        path[t + 1] = path[t] * np.exp(drift + vol_term * z_col[t])
    return path[1:]


def _simulate_log_vol_ou(params: f.LogVolOUParams, z_col: np.ndarray, dt: float) -> np.ndarray:
    n = len(z_col)
    log_level = np.log(params.level0)
    path = np.empty(n + 1)
    path[0] = log_level
    for t in range(n):
        drift = params.kappa * (log_level - path[t]) * dt
        diffusion = params.sigma * np.sqrt(dt) * z_col[t]
        path[t + 1] = path[t] + drift + diffusion
    return np.exp(path[1:])


def _simulate_cir(params: f.CIRParams, z_col: np.ndarray, dt: float) -> np.ndarray:
    """Esquema de truncamento total (Lord/Koekkoek/Van Dijk): usa max(x, 0) sob
    a raiz para nunca propagar um número negativo pro sqrt, e piso final em 0."""
    n = len(z_col)
    path = np.empty(n + 1)
    path[0] = params.r0
    for t in range(n):
        x_pos = max(path[t], 0.0)
        drift = params.kappa * (params.theta - x_pos) * dt
        diffusion = params.sigma * np.sqrt(x_pos) * np.sqrt(dt) * z_col[t]
        path[t + 1] = max(path[t] + drift + diffusion, 0.0)
    return path[1:]


def generate_risk_factors(
    seed: int = f.SEED, n_obs: int = f.N_OBSERVATIONS, correlation_matrix: np.ndarray | None = None
) -> dict[str, pd.Series]:
    """`correlation_matrix` é só para gerar datasets paralelos de CENÁRIO (ex.:
    quebra de correlação, CLAUDE.md §5.4/§7 `scenario_builder.py`) — nunca para
    regenerar o histórico congelado em `data/risk_factors/` (§5.3), que sempre
    usa a matriz estrutural default de `factors.py`."""
    dt = 1.0 / f.TRADING_DAYS_PER_YEAR
    dates = pd.bdate_range(start=START_DATE, periods=n_obs)

    corr = correlation_matrix if correlation_matrix is not None else f.build_correlation_matrix()
    chol = np.linalg.cholesky(corr)

    rng = np.random.default_rng(seed)
    independent_z = rng.standard_normal(size=(n_obs, len(f.FACTOR_NAMES)))
    correlated_z = independent_z @ chol.T  # cada coluna ~ N(0,1), correlacionadas conforme `corr`

    z_by_factor = {name: correlated_z[:, i] for i, name in enumerate(f.FACTOR_NAMES)}

    series: dict[str, pd.Series] = {}
    for name, params in f.CURVES.items():
        series[name] = pd.Series(_simulate_vasicek(params, z_by_factor[name], dt), index=dates, name=name)
    for name, params in f.SPOTS.items():
        series[name] = pd.Series(_simulate_gbm(params, z_by_factor[name], dt), index=dates, name=name)
    for name, params in f.VOLS.items():
        series[name] = pd.Series(_simulate_log_vol_ou(params, z_by_factor[name], dt), index=dates, name=name)
    for name, params in f.SPREADS.items():
        series[name] = pd.Series(_simulate_cir(params, z_by_factor[name], dt), index=dates, name=name)
    for name, params in f.BEHAVIORAL.items():
        series[name] = pd.Series(_simulate_cir(params, z_by_factor[name], dt), index=dates, name=name)

    return series


def generate_correlation_matrix_df() -> pd.DataFrame:
    corr = f.build_correlation_matrix()
    return pd.DataFrame(corr, index=f.FACTOR_NAMES, columns=f.FACTOR_NAMES)


def freeze(output_dir: Path = DATA_DIR, seed: int = f.SEED, n_obs: int = f.N_OBSERVATIONS) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    series = generate_risk_factors(seed=seed, n_obs=n_obs)
    for name, s in series.items():
        df = s.rename("value").rename_axis("date").reset_index()
        df.to_csv(output_dir / f"{name}.csv", index=False)

    corr_df = generate_correlation_matrix_df()
    corr_df.to_csv(output_dir / "correlation_matrix.csv")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", action="store_true", help="gera e grava os CSVs em data/risk_factors/")
    parser.add_argument("--output-dir", default=str(DATA_DIR))
    args = parser.parse_args(argv)

    if not args.freeze:
        parser.error("este script só faz sentido com --freeze (§5.3 — geração é deliberada, nunca automática)")

    freeze(output_dir=Path(args.output_dir))
    print(f"{len(f.FACTOR_NAMES)} fatores de risco congelados em {args.output_dir} ({f.N_OBSERVATIONS} obs. cada).")
    return 0


if __name__ == "__main__":  # pragma: no cover - só roda via `python -m --freeze`, não sob pytest
    raise SystemExit(main())
