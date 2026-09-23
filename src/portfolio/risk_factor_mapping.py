"""Fragmentação instrumento → fatores de risco (CLAUDE.md §5.2/§5.3).

A fonte única de verdade é `Position.risk_factors` em `base_portfolio.py`
(artefato congelado); este módulo só expõe consultas sobre essa fragmentação,
sem duplicar o dado — evita o mapeamento e a definição de posição divergirem
com o tempo.
"""

from __future__ import annotations

from .base_portfolio import POSITIONS, Position


def get_risk_factors(position_id: int) -> tuple[str, ...]:
    for position in POSITIONS:
        if position.id == position_id:
            return position.risk_factors
    raise KeyError(f"posição desconhecida: {position_id}")


def positions_using_factor(factor_name: str) -> list[int]:
    return [p.id for p in POSITIONS if factor_name in p.risk_factors]


def all_factors_used() -> set[str]:
    factors: set[str] = set()
    for position in POSITIONS:
        factors.update(position.risk_factors)
    return factors


def build_mapping_table() -> list[dict]:
    """Tabela instrumento × fatores, no formato usado pelo relatório final
    (§9.2) — uma linha por posição, fatores como string separada por vírgula."""
    return [
        {
            "id": p.id,
            "name": p.name,
            "asset_class": p.asset_class,
            "risk_factors": ", ".join(p.risk_factors),
        }
        for p in POSITIONS
    ]


def positions_for_scope(*, banking_book_only: bool = False) -> list[Position]:
    from .base_portfolio import BANKING_BOOK_POSITION_IDS

    if banking_book_only:
        return [p for p in POSITIONS if p.id in BANKING_BOOK_POSITION_IDS]
    return list(POSITIONS)
