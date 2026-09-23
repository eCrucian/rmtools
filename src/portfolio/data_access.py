"""Leitura somente-leitura dos fatores de risco congelados (CLAUDE.md §5.3).

Único ponto de entrada que o PIPELINE (Actions 01-10) deve usar para ler
`data/risk_factors/*.csv`. Nunca gera dado — se o CSV não existe, é erro
(o freeze é uma etapa manual e deliberada, `risk_factor_generator.py --freeze`).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import factors as f

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data" / "risk_factors"


def load_risk_factor(name: str) -> pd.Series:
    path = DATA_DIR / f"{name}.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"fator de risco '{name}' não está congelado em {path} — rode "
            "`python -m src.portfolio.risk_factor_generator --freeze` (§5.3)."
        )
    df = pd.read_csv(path, parse_dates=["date"])
    return df.set_index("date")["value"].rename(name)


def load_all_risk_factors() -> dict[str, pd.Series]:
    return {name: load_risk_factor(name) for name in f.FACTOR_NAMES}


def load_correlation_matrix() -> pd.DataFrame:
    path = DATA_DIR / "correlation_matrix.csv"
    if not path.exists():
        raise FileNotFoundError(f"matriz de correlação não está congelada em {path} (§5.3).")
    return pd.read_csv(path, index_col=0)
