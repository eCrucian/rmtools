"""Carteira hipotética de referência — FIXA (CLAUDE.md §5.1/§5.3).

Artefato congelado: existe desde o primeiro setup do repositório e não é
recalculado em tempo de execução pelo pipeline. Adicionar/corrigir um
instrumento é uma mudança deliberada e versionada (novo commit), nunca efeito
colateral de rodar uma validação (§5.3/§6.8).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Position:
    id: int
    name: str
    asset_class: str
    currency: str  # "BRL" | "USD"
    direction: int  # +1 comprado/ativo, -1 vendido/passivo
    notional: float
    risk_factors: tuple[str, ...]
    pricer: str  # chave dispatchada em pricing_models.price_position
    params: dict = field(default_factory=dict)


POSITIONS: list[Position] = [
    Position(
        id=1, name="LFT (Tesouro Selic)", asset_class="renda_fixa_publica_br", currency="BRL",
        direction=1, notional=10_000_000.0, risk_factors=("di_pre",), pricer="par_floater",
        params={"curve": "di_pre", "reference_rate": 0.1075, "residual_duration": 0.05},
    ),
    Position(
        id=2, name="NTN-B", asset_class="renda_fixa_publica_br_indexada", currency="BRL",
        direction=1, notional=5_000_000.0, risk_factors=("ipca_real",), pricer="fixed_bond",
        params={"curve": "ipca_real", "coupon": 0.06, "tenor_years": 8.0, "freq": 2},
    ),
    Position(
        id=3, name="NTN-F", asset_class="renda_fixa_publica_br_prefixada", currency="BRL",
        direction=1, notional=5_000_000.0, risk_factors=("pre_nominal",), pricer="fixed_bond",
        params={"curve": "pre_nominal", "coupon": 0.10, "tenor_years": 6.0, "freq": 2},
    ),
    Position(
        id=4, name="LTN", asset_class="renda_fixa_publica_br_prefixada_zero", currency="BRL",
        direction=1, notional=3_000_000.0, risk_factors=("pre_nominal",), pricer="zero_bond",
        params={"curve": "pre_nominal", "tenor_years": 2.0},
    ),
    Position(
        id=5, name="Debêntures (CDI+spread)", asset_class="credito_privado_br", currency="BRL",
        direction=1, notional=4_000_000.0, risk_factors=("di_pre", "spread_debentures"), pricer="credit_bond",
        params={"curve": "di_pre", "spread_curve": "spread_debentures", "coupon": 0.12, "tenor_years": 4.0, "freq": 2},
    ),
    Position(
        id=6, name="Bonds corporativos (USD)", asset_class="credito_privado_internacional", currency="USD",
        direction=1, notional=2_000_000.0, risk_factors=("ust", "spread_bonds_corp", "usdbrl"), pricer="credit_bond",
        params={"curve": "ust", "spread_curve": "spread_bonds_corp", "coupon": 0.06, "tenor_years": 5.0, "freq": 2},
    ),
    Position(
        id=7, name="US Treasuries", asset_class="renda_fixa_soberana_us", currency="USD",
        direction=1, notional=3_000_000.0, risk_factors=("ust",), pricer="fixed_bond",
        params={"curve": "ust", "coupon": 0.045, "tenor_years": 10.0, "freq": 2},
    ),
    Position(
        id=8, name="Opção de IBOV — europeia", asset_class="derivativo_acoes_br", currency="BRL",
        direction=1, notional=100.0, risk_factors=("ibov", "vol_ibov", "di_pre"), pricer="black_scholes",
        params={"underlying": "ibov", "vol": "vol_ibov", "rate": "di_pre", "strike": 130_000.0, "tenor_years": 0.5, "option_type": "call"},
    ),
    Position(
        id=9, name="Opção de IBOV — americana", asset_class="derivativo_acoes_br", currency="BRL",
        direction=1, notional=100.0, risk_factors=("ibov", "vol_ibov", "di_pre"), pricer="binomial_american",
        params={"underlying": "ibov", "vol": "vol_ibov", "rate": "di_pre", "strike": 128_000.0, "tenor_years": 0.5, "option_type": "put", "steps": 40},
    ),
    Position(
        id=10, name="Opção de SPX — europeia", asset_class="derivativo_acoes_us", currency="USD",
        direction=1, notional=50.0, risk_factors=("spx", "vol_spx", "sofr"), pricer="black_scholes",
        params={"underlying": "spx", "vol": "vol_spx", "rate": "sofr", "strike": 5_300.0, "tenor_years": 0.5, "option_type": "call"},
    ),
    Position(
        id=11, name="Opção de SPX — americana", asset_class="derivativo_acoes_us", currency="USD",
        direction=1, notional=50.0, risk_factors=("spx", "vol_spx", "sofr"), pricer="binomial_american",
        params={"underlying": "spx", "vol": "vol_spx", "rate": "sofr", "strike": 5_100.0, "tenor_years": 0.5, "option_type": "put", "steps": 40},
    ),
    Position(
        id=12, name="Opção de USD/BRL — europeia", asset_class="derivativo_cambial", currency="BRL",
        direction=1, notional=1_000_000.0, risk_factors=("usdbrl", "vol_usdbrl", "di_pre", "sofr"), pricer="fx_black_scholes",
        params={"underlying": "usdbrl", "vol": "vol_usdbrl", "rate_domestic": "di_pre", "rate_foreign": "sofr", "strike": 5.20, "tenor_years": 0.25, "option_type": "call"},
    ),
    Position(
        id=13, name="Opção de USD/BRL — americana", asset_class="derivativo_cambial", currency="BRL",
        direction=1, notional=1_000_000.0, risk_factors=("usdbrl", "vol_usdbrl", "di_pre", "sofr"), pricer="fx_binomial_american",
        params={"underlying": "usdbrl", "vol": "vol_usdbrl", "rate_domestic": "di_pre", "rate_foreign": "sofr", "strike": 4.90, "tenor_years": 0.25, "option_type": "put", "steps": 40},
    ),
    Position(
        id=14, name="Swap com limitador (collar) CDI x Pré", asset_class="derivativo_juros_br", currency="BRL",
        direction=1, notional=5_000_000.0, risk_factors=("di_pre", "pre_nominal", "vol_juros"), pricer="collar_swap",
        params={"pay_curve": "di_pre", "receive_curve": "pre_nominal", "cap_rate": 0.13, "floor_rate": 0.09, "vol": "vol_juros", "tenor_years": 3.0},
    ),
    Position(
        id=15, name="Swap com limitador IPCA x Pré", asset_class="derivativo_juros_br", currency="BRL",
        direction=1, notional=4_000_000.0, risk_factors=("ipca_real", "pre_nominal", "vol_juros"), pricer="collar_swap",
        params={"pay_curve": "ipca_real", "receive_curve": "pre_nominal", "cap_rate": 0.12, "floor_rate": 0.07, "vol": "vol_juros", "tenor_years": 4.0},
    ),
    Position(
        id=16, name="Swap com limitador USD x SOFR", asset_class="derivativo_juros_cross_currency", currency="USD",
        direction=1, notional=3_000_000.0, risk_factors=("sofr", "fed_funds", "vol_juros", "usdbrl"), pricer="collar_swap",
        params={"pay_curve": "fed_funds", "receive_curve": "sofr", "cap_rate": 0.06, "floor_rate": 0.03, "vol": "vol_juros", "tenor_years": 5.0},
    ),
    Position(
        id=17, name="Futuro de Fed Funds", asset_class="derivativo_juros_us", currency="USD",
        direction=1, notional=10_000_000.0, risk_factors=("fed_funds",), pricer="rate_future",
        params={"curve": "fed_funds", "reference_rate": 0.0525, "dv01_years": 0.25},
    ),
    Position(
        id=18, name="Futuro de Treasury", asset_class="derivativo_juros_us", currency="USD",
        direction=1, notional=2_000_000.0, risk_factors=("ust",), pricer="rate_future",
        params={"curve": "ust", "reference_rate": 0.045, "dv01_years": 7.0},
    ),
    Position(
        id=19, name="Futuro de Dólar (DOL)", asset_class="derivativo_cambial_br", currency="BRL",
        direction=1, notional=5_000_000.0, risk_factors=("usdbrl", "di_pre", "sofr"), pricer="fx_forward",
        params={"spot": "usdbrl", "domestic_curve": "di_pre", "foreign_curve": "sofr", "contract_rate": 5.05, "tenor_years": 0.17},
    ),
    Position(
        id=20, name="NDF de dólar", asset_class="derivativo_cambial_br_balcao", currency="BRL",
        direction=1, notional=2_000_000.0, risk_factors=("usdbrl", "di_pre", "sofr"), pricer="fx_forward",
        params={"spot": "usdbrl", "domestic_curve": "di_pre", "foreign_curve": "sofr", "contract_rate": 5.10, "tenor_years": 0.25},
    ),
    Position(
        # notional em unidades do subjacente (não em BRL/USD) — dimensionado para
        # ~USD 2mm de exposição no nível de preço inicial (spot0=1_350, §5.3
        # factors.py): 1_500 * 1_350 ≈ 2.0mm.
        id=21, name="NDF asiática (average rate) — soja", asset_class="derivativo_commodity", currency="USD",
        direction=1, notional=1_500.0, risk_factors=("soja",), pricer="asian_forward",
        params={"spot": "soja", "discount_curve": "sofr", "contract_rate": 1_360.0, "tenor_years": 0.5},
    ),
    Position(
        # idem — dimensionado para ~USD 1.5mm de exposição no spot0=82 (brent).
        id=22, name="NDF asiática (average rate) — petróleo", asset_class="derivativo_commodity", currency="USD",
        direction=1, notional=18_000.0, risk_factors=("brent",), pricer="asian_forward",
        params={"spot": "brent", "discount_curve": "sofr", "contract_rate": 80.0, "tenor_years": 0.5},
    ),
    Position(
        id=23, name="Bond com opção de pré-pagamento (callable/MBS-like)", asset_class="renda_fixa_estruturada", currency="BRL",
        direction=1, notional=6_000_000.0, risk_factors=("pre_nominal", "spread_debentures", "cpr", "vol_juros"), pricer="prepayable_bond",
        params={"curve": "pre_nominal", "spread_curve": "spread_debentures", "cpr_factor": "cpr", "vol_curve": "vol_juros", "coupon": 0.10, "tenor_years": 15.0},
    ),
    Position(
        id=24, name="Opção quanto (SPX, payoff em BRL a taxa fixa)", asset_class="derivativo_estruturado", currency="BRL",
        direction=1, notional=10.0, risk_factors=("spx", "vol_spx", "vol_usdbrl", "di_pre"), pricer="quanto_option",
        params={
            "underlying": "spx", "vol": "vol_spx", "fx_vol": "vol_usdbrl", "rate_domestic": "di_pre",
            "correlation": -0.10, "strike": 5_200.0, "tenor_years": 0.5, "option_type": "call",
        },
    ),
    Position(
        id=25, name="Depósitos sem vencimento (NMD)", asset_class="carteira_bancaria_passivo", currency="BRL",
        direction=-1, notional=8_000_000.0, risk_factors=("di_pre", "nmd_decay_rate"), pricer="nmd_liability",
        params={"curve": "di_pre", "decay_factor": "nmd_decay_rate"},
    ),
    Position(
        id=26, name="Carteira de crédito com pré-pagamento", asset_class="carteira_bancaria_ativo", currency="BRL",
        direction=1, notional=7_000_000.0, risk_factors=("pre_nominal", "spread_debentures", "cpr"), pricer="credit_portfolio",
        params={
            "curve": "pre_nominal", "spread_curve": "spread_debentures", "cpr_factor": "cpr",
            "default_rate": 0.02, "coupon": 0.14, "tenor_years": 5.0,
        },
    ),
]

POSITIONS_BY_ID: dict[int, Position] = {p.id: p for p in POSITIONS}

# Instrumentos obrigatórios sempre que a métrica em validação for de carteira
# bancária (EVE/NII/IRRBB) — CLAUDE.md §5.1.
BANKING_BOOK_POSITION_IDS: tuple[int, ...] = (23, 25, 26)
