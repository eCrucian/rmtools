"""Master list de fatores de risco (CLAUDE.md §5.2) e parâmetros de calibração
usados pelo gerador (§5.3). Os valores numéricos aqui são as premissas de
nível/vol/reversão "plausíveis de mercado" exigidas por §5.3 — documentadas
também (como registro histórico) em config/risk_factors.yaml após o freeze.

Estes parâmetros são consumidos SÓ por `risk_factor_generator.py --freeze`,
nunca pelo pipeline em tempo de execução (§5.3 — regra dura de dados
congelados). Depois do freeze, o pipeline só lê os CSVs em data/risk_factors/.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

SEED = 20260101  # fixo e documentado (§5.3) — nunca mudar após o freeze

N_OBSERVATIONS = 1000
TRADING_DAYS_PER_YEAR = 252


@dataclass(frozen=True)
class VasicekParams:
    r0: float
    theta: float  # nível de longo prazo
    kappa: float  # velocidade de reversão
    sigma: float  # vol anualizada
    floor: float = -0.02  # taxas nominais podem ficar levemente negativas


@dataclass(frozen=True)
class CIRParams:
    """Usado para spreads e fatores comportamentais — não-negativos por construção
    (processo CIR: sigma * sqrt(max(x, 0)) * dW)."""

    r0: float
    theta: float
    kappa: float
    sigma: float


@dataclass(frozen=True)
class GBMParams:
    s0: float
    mu: float  # drift anualizado
    sigma: float  # vol anualizada


@dataclass(frozen=True)
class LogVolOUParams:
    """Vol estocástica simples: OU no log da vol (§5.3 — evita vol constante)."""

    level0: float
    kappa: float
    sigma: float  # vol do log-vol


CURVES: dict[str, VasicekParams] = {
    "di_pre": VasicekParams(r0=0.1075, theta=0.10, kappa=0.15, sigma=0.015),
    "ipca_real": VasicekParams(r0=0.055, theta=0.05, kappa=0.10, sigma=0.008),
    "pre_nominal": VasicekParams(r0=0.115, theta=0.105, kappa=0.12, sigma=0.016),
    "ust": VasicekParams(r0=0.045, theta=0.04, kappa=0.08, sigma=0.007),
    "sofr": VasicekParams(r0=0.050, theta=0.045, kappa=0.10, sigma=0.006),
    "fed_funds": VasicekParams(r0=0.0525, theta=0.045, kappa=0.08, sigma=0.006),
}

SPOTS: dict[str, GBMParams] = {
    "usdbrl": GBMParams(s0=5.00, mu=0.00, sigma=0.16),
    "ibov": GBMParams(s0=125_000.0, mu=0.08, sigma=0.22),
    "spx": GBMParams(s0=5_200.0, mu=0.08, sigma=0.16),
    "soja": GBMParams(s0=1_350.0, mu=0.00, sigma=0.20),
    "brent": GBMParams(s0=82.0, mu=0.00, sigma=0.30),
    "wti": GBMParams(s0=78.0, mu=0.00, sigma=0.32),
}

VOLS: dict[str, LogVolOUParams] = {
    "vol_ibov": LogVolOUParams(level0=0.22, kappa=0.20, sigma=0.15),
    "vol_spx": LogVolOUParams(level0=0.16, kappa=0.20, sigma=0.15),
    "vol_usdbrl": LogVolOUParams(level0=0.14, kappa=0.20, sigma=0.12),
    "vol_juros": LogVolOUParams(level0=0.18, kappa=0.15, sigma=0.10),
}

SPREADS: dict[str, CIRParams] = {
    "spread_debentures": CIRParams(r0=0.025, theta=0.022, kappa=0.15, sigma=0.006),
    "spread_bonds_corp": CIRParams(r0=0.018, theta=0.015, kappa=0.12, sigma=0.005),
}

BEHAVIORAL: dict[str, CIRParams] = {
    "nmd_decay_rate": CIRParams(r0=0.15, theta=0.15, kappa=0.20, sigma=0.02),
    "cpr": CIRParams(r0=0.12, theta=0.12, kappa=0.25, sigma=0.03),
}

FACTOR_NAMES: list[str] = (
    list(CURVES) + list(SPOTS) + list(VOLS) + list(SPREADS) + list(BEHAVIORAL)
)

# Correlações estruturais deliberadas (§5.2 — matriz completa e explícita, não
# implícita). Pares não listados default para 0 (exceto diagonal = 1). Valores
# plausíveis, não calibrados a dado real — carteira é sintética/de referência.
_RAW_CORRELATIONS: list[tuple[str, str, float]] = [
    ("di_pre", "pre_nominal", 0.85),
    ("di_pre", "ipca_real", 0.30),
    ("pre_nominal", "ipca_real", 0.25),
    ("ust", "sofr", 0.90),
    ("ust", "fed_funds", 0.80),
    ("sofr", "fed_funds", 0.85),
    ("di_pre", "ust", 0.20),
    ("pre_nominal", "ust", 0.15),
    ("usdbrl", "ibov", -0.45),
    ("usdbrl", "vol_usdbrl", 0.35),
    ("ibov", "vol_ibov", -0.55),
    ("spx", "vol_spx", -0.60),
    ("usdbrl", "spx", -0.10),
    ("usdbrl", "brent", -0.20),
    ("usdbrl", "wti", -0.20),
    ("brent", "wti", 0.95),
    ("ibov", "spx", 0.40),
    ("pre_nominal", "vol_juros", 0.25),
    ("di_pre", "vol_juros", 0.20),
    ("cpr", "pre_nominal", -0.40),
    ("cpr", "di_pre", -0.30),
    ("nmd_decay_rate", "di_pre", 0.25),
    ("spread_debentures", "di_pre", 0.15),
    ("spread_debentures", "ibov", -0.20),
    ("spread_bonds_corp", "ust", 0.15),
    ("spread_bonds_corp", "spx", -0.20),
    ("spread_debentures", "spread_bonds_corp", 0.40),
    ("soja", "usdbrl", -0.15),
]


def build_correlation_matrix() -> np.ndarray:
    """Monta a matriz de correlação completa (§5.2) a partir dos pares
    estruturais acima, e a corrige para a mais próxima matriz semidefinida
    positiva (autovalores negativos por inconsistência entre pares são
    zerados) — necessário para decompor via Cholesky no gerador."""
    n = len(FACTOR_NAMES)
    idx = {name: i for i, name in enumerate(FACTOR_NAMES)}
    corr = np.eye(n)
    for a, b, rho in _RAW_CORRELATIONS:
        i, j = idx[a], idx[b]
        corr[i, j] = rho
        corr[j, i] = rho
    return nearest_psd(corr)


def nearest_psd(matrix: np.ndarray) -> np.ndarray:
    eigvals, eigvecs = np.linalg.eigh(matrix)
    eigvals_clipped = np.clip(eigvals, 1e-10, None)
    repaired = eigvecs @ np.diag(eigvals_clipped) @ eigvecs.T
    # renormaliza para diagonal = 1 (a correção de autovalores pode alterá-la levemente)
    d = np.sqrt(np.diag(repaired))
    repaired = repaired / np.outer(d, d)
    np.fill_diagonal(repaired, 1.0)
    return repaired
