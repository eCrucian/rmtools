"""Customização automática / cenários limítrofes (CLAUDE.md §5.4).

Gera variantes a partir da carteira base (`base_portfolio.POSITIONS`, nunca
modificada em si — §5.3/§6.8) e overrides de mercado para os cenários
comportamentais. `POSITIONS` é sempre o ponto de partida (`dataclasses.replace`
produz cópias, nunca muta o original).
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from . import factors as f
from .base_portfolio import POSITIONS, Position
from .pricing_models import MarketSnapshot
from .risk_factor_generator import generate_risk_factors

HIGH_OPTIONALITY_IDS: tuple[int, ...] = (8, 9, 10, 11, 12, 13, 17)
PREPAYMENT_POSITION_IDS: tuple[int, ...] = (23, 26)


def _zeroed(position: Position) -> Position:
    return replace(position, notional=0.0)


def directional_variant(positions: list[Position] = POSITIONS, *, keep: int) -> list[Position]:
    """Zera as posições do sinal oposto a `keep` (+1 comprado / -1 vendido),
    deixando a carteira fortemente direcional (§5.4)."""
    if keep not in (1, -1):
        raise ValueError("keep deve ser +1 (comprado) ou -1 (vendido)")
    return [p if p.direction == keep else _zeroed(p) for p in positions]


def concentrated_variant(positions: list[Position] = POSITIONS, *, factor_name: str) -> list[Position]:
    """Concentra notional num único fator de risco: zera toda posição que não
    referencia `factor_name` (§5.4 — teste de concentração/tail)."""
    if factor_name not in f.FACTOR_NAMES:
        raise ValueError(f"fator de risco desconhecido: {factor_name!r}")
    return [p if factor_name in p.risk_factors else _zeroed(p) for p in positions]


def _tenor_years(position: Position) -> float | None:
    return position.params.get("tenor_years")


def short_tenor_variant(positions: list[Position] = POSITIONS, *, threshold_years: float = 3.0) -> list[Position]:
    """Só instrumentos de prazo curto (§5.4) — zera os de prazo >= threshold e
    os que não têm tenor definido (ex.: LFT/futuros linearizados, sem tenor
    contratual de fluxo de caixa nesta modelagem simplificada)."""
    result = []
    for p in positions:
        tenor = _tenor_years(p)
        result.append(p if (tenor is not None and tenor < threshold_years) else _zeroed(p))
    return result


def long_tenor_variant(positions: list[Position] = POSITIONS, *, threshold_years: float = 3.0) -> list[Position]:
    """Só instrumentos de prazo longo (§5.4) — complemento de `short_tenor_variant`."""
    result = []
    for p in positions:
        tenor = _tenor_years(p)
        result.append(p if (tenor is not None and tenor >= threshold_years) else _zeroed(p))
    return result


def high_optionality_variant(positions: list[Position] = POSITIONS, *, scale: float = 5.0) -> list[Position]:
    """Pondera para cima os instrumentos gamma/vega heavy (§5.4 — opções e o
    futuro de Fed Funds, sensível à convexidade de expectativas de juros
    curtos) multiplicando o notional por `scale`; os demais ficam inalterados."""
    return [replace(p, notional=p.notional * scale) if p.id in HIGH_OPTIONALITY_IDS else p for p in positions]


def nmd_stress_market(market: MarketSnapshot, *, direction: str, multiplier: float = 0.5) -> MarketSnapshot:
    """Alongamento (`multiplier < 1`, decaimento mais lento => vida efetiva
    maior) ou encurtamento (`multiplier > 1`) do prazo comportamental do NMD
    (§5.4). Retorna uma cópia do snapshot — nunca muta `market` no lugar."""
    if direction not in ("alongamento", "encurtamento"):
        raise ValueError("direction deve ser 'alongamento' ou 'encurtamento'")
    factor = multiplier if direction == "encurtamento" else (1.0 / multiplier)
    stressed = dict(market)
    stressed["nmd_decay_rate"] = market["nmd_decay_rate"] * factor
    return stressed


def prepayment_stress_market(market: MarketSnapshot, *, direction: str, multiplier: float = 1.5) -> MarketSnapshot:
    """Choque de CPR para cima (`direction="alta"` — refinanciamento em massa)
    ou para baixo (`direction="baixa"` — retenção), §5.4, aplicado aos
    instrumentos 23/26. Retorna uma cópia do snapshot."""
    if direction not in ("alta", "baixa"):
        raise ValueError("direction deve ser 'alta' ou 'baixa'")
    factor = multiplier if direction == "alta" else (1.0 / multiplier)
    stressed = dict(market)
    stressed["cpr"] = market["cpr"] * factor
    return stressed


def stressed_correlation_matrix(target_off_diagonal: float = 0.90) -> np.ndarray:
    """Cenário de quebra de correlação (§5.4/§Action 04/07) — "tudo cai/sobe
    junto": todas as correlações fora da diagonal viram `target_off_diagonal`,
    depois corrigido para a matriz PSD mais próxima (mesma técnica de
    `factors.nearest_psd`)."""
    n = len(f.FACTOR_NAMES)
    stressed = np.full((n, n), target_off_diagonal)
    np.fill_diagonal(stressed, 1.0)
    return f.nearest_psd(stressed)


def generate_correlation_break_dataset(
    seed: int = f.SEED, n_obs: int = f.N_OBSERVATIONS, target_off_diagonal: float = 0.90
):
    """Gera um segundo dataset PARALELO (§5.4) sob a matriz de correlação
    estressada — nunca sobrescreve nem deriva de `data/risk_factors/` (§5.3);
    é recalculado sob demanda pela Action 04/07, não persistido como fixture."""
    stressed_corr = stressed_correlation_matrix(target_off_diagonal)
    return generate_risk_factors(seed=seed, n_obs=n_obs, correlation_matrix=stressed_corr)
