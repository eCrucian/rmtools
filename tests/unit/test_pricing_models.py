from __future__ import annotations

import math

import pytest

from src.portfolio import pricing_models as pm
from src.portfolio.base_portfolio import Position


# --------------------------------------------------------------------------
# Helpers de desconto / renda fixa
# --------------------------------------------------------------------------

def test_discount_factor_zero_tenor_is_one():
    assert pm.discount_factor(0.10, 0.0) == 1.0


def test_discount_factor_base_case():
    assert math.isclose(pm.discount_factor(0.10, 1.0), 1 / 1.10, rel_tol=1e-12)


def test_discount_factor_semiannual_freq():
    assert math.isclose(pm.discount_factor(0.10, 1.0, freq=2), (1 + 0.05) ** -2, rel_tol=1e-12)


def test_annuity_factor_zero_rate_edge_case():
    assert pm.annuity_factor(0.0, 5.0) == 5.0


def test_annuity_factor_base_case():
    expected = (1 - (1.1) ** -5) / 0.10
    assert math.isclose(pm.annuity_factor(0.10, 5.0), expected, rel_tol=1e-12)


def test_fixed_bond_pv_par_identity_when_coupon_equals_ytm():
    pv = pm.fixed_bond_pv(face=1000.0, coupon_rate=0.08, tenor_years=7, freq=2, ytm=0.08)
    assert math.isclose(pv, 1000.0, rel_tol=1e-6)


def test_fixed_bond_pv_zero_tenor_edge_case():
    assert pm.fixed_bond_pv(face=1000.0, coupon_rate=0.08, tenor_years=0.0, freq=2, ytm=0.20) == 1000.0


def test_fixed_bond_pv_discount_bond_below_par():
    pv = pm.fixed_bond_pv(face=1000.0, coupon_rate=0.05, tenor_years=5, freq=1, ytm=0.10)
    assert pv < 1000.0


def test_zero_bond_pv_known_value():
    assert math.isclose(pm.zero_bond_pv(1000.0, 2.0, 0.10), 1000.0 / 1.21, rel_tol=1e-12)


# --------------------------------------------------------------------------
# Opções
# --------------------------------------------------------------------------

def test_black_scholes_put_call_parity():
    spot, strike, rate, vol, t = 100.0, 95.0, 0.05, 0.25, 0.75
    call = pm.black_scholes(spot, strike, rate, vol, t, "call")
    put = pm.black_scholes(spot, strike, rate, vol, t, "put")
    parity_rhs = spot - strike * math.exp(-rate * t)
    assert math.isclose(call - put, parity_rhs, rel_tol=1e-9)


def test_black_scholes_deep_itm_call_approaches_intrinsic():
    price = pm.black_scholes(spot=1000.0, strike=100.0, rate=0.05, vol=0.2, t=0.5, option_type="call")
    intrinsic = 1000.0 - 100.0 * math.exp(-0.05 * 0.5)
    assert math.isclose(price, intrinsic, rel_tol=1e-3)


def test_black_scholes_invalid_tenor_raises():
    with pytest.raises(ValueError):
        pm.black_scholes(100.0, 100.0, 0.05, 0.2, 0.0, "call")


def test_black_scholes_invalid_vol_raises():
    with pytest.raises(ValueError):
        pm.black_scholes(100.0, 100.0, 0.05, 0.0, 1.0, "call")


def test_black_scholes_invalid_option_type_raises():
    with pytest.raises(ValueError):
        pm.black_scholes(100.0, 100.0, 0.05, 0.2, 1.0, "straddle")


def test_binomial_american_put_is_at_least_european_put():
    kwargs = dict(spot=100.0, strike=105.0, rate=0.05, vol=0.3, t=1.0, option_type="put")
    european = pm.black_scholes(**kwargs)
    american = pm.binomial_american(**kwargs, steps=60)
    assert american >= european - 1e-6


def test_binomial_american_call_no_dividend_close_to_european():
    kwargs = dict(spot=100.0, strike=100.0, rate=0.05, vol=0.2, t=1.0, option_type="call")
    european = pm.black_scholes(**kwargs)
    american = pm.binomial_american(**kwargs, steps=80)
    assert math.isclose(american, european, rel_tol=1e-2)


def test_binomial_american_invalid_steps_raises():
    with pytest.raises(ValueError):
        pm.binomial_american(100.0, 100.0, 0.05, 0.2, 1.0, "call", steps=0)


def test_binomial_american_invalid_option_type_raises():
    with pytest.raises(ValueError):
        pm.binomial_american(100.0, 100.0, 0.05, 0.2, 1.0, "exotic", steps=10)


def test_binomial_american_invalid_tenor_raises():
    with pytest.raises(ValueError):
        pm.binomial_american(100.0, 100.0, 0.05, 0.2, 0.0, "call", steps=10)


def test_binomial_american_invalid_risk_neutral_probability_raises():
    # rate alta demais e vol baixa demais para o dt grosseiro (steps=2, t=5)
    # geram uma probabilidade neutra ao risco fora de [0, 1] — parâmetros
    # numericamente inconsistentes, não um regime de mercado plausível.
    with pytest.raises(ValueError):
        pm.binomial_american(100.0, 100.0, rate=2.0, vol=0.05, t=5.0, option_type="call", steps=2)


def test_quanto_option_zero_correlation_matches_plain_carry():
    price = pm.quanto_option(
        spot=100.0, strike=100.0, rate_domestic=0.05, vol=0.2, fx_vol=0.15, correlation=0.0, t=1.0, option_type="call"
    )
    plain = pm.black_scholes(100.0, 100.0, 0.05, 0.2, 1.0, "call", carry=0.05)
    assert math.isclose(price, plain, rel_tol=1e-9)


def test_quanto_option_negative_correlation_changes_price():
    base = pm.quanto_option(100.0, 100.0, 0.05, 0.2, 0.15, 0.0, 1.0, "call")
    shifted = pm.quanto_option(100.0, 100.0, 0.05, 0.2, 0.15, -0.5, 1.0, "call")
    assert base != shifted


# --------------------------------------------------------------------------
# Cap/floor e swap com limitador
# --------------------------------------------------------------------------

def test_black76_cap_floor_degenerate_nonpositive_forward_uses_intrinsic():
    value = pm.black76_cap_floor(forward_rate=-0.01, strike_rate=0.05, vol=0.2, t=1.0, notional=1000.0, kind="cap")
    assert value == 0.0  # forward < strike, intrinsic de um cap é 0


def test_black76_cap_floor_invalid_kind_raises():
    with pytest.raises(ValueError):
        pm.black76_cap_floor(0.10, 0.08, 0.2, 1.0, 1000.0, kind="collar")


def test_black76_cap_floor_cap_and_floor_are_nonnegative():
    cap = pm.black76_cap_floor(0.10, 0.08, 0.2, 1.0, 1000.0, kind="cap")
    floor = pm.black76_cap_floor(0.10, 0.12, 0.2, 1.0, 1000.0, kind="floor")
    assert cap >= 0
    assert floor >= 0


def test_collar_swap_runs_and_returns_float():
    pv = pm.collar_swap(notional=1_000_000.0, pay_rate=0.10, receive_rate=0.11, cap_rate=0.13, floor_rate=0.09, vol=0.15, tenor_years=3.0)
    assert isinstance(pv, float)


# --------------------------------------------------------------------------
# Futuros / a termo
# --------------------------------------------------------------------------

def test_rate_future_pv_zero_when_curve_equals_reference():
    assert pm.rate_future_pv(notional=1_000_000.0, curve_rate=0.05, reference_rate=0.05, dv01_years=5.0) == 0.0


def test_rate_future_pv_sign_convention():
    # taxa subiu em relação à referência -> perda para quem está comprado no futuro (posição linearizada)
    pv = pm.rate_future_pv(notional=1_000_000.0, curve_rate=0.06, reference_rate=0.05, dv01_years=5.0)
    assert pv < 0


def test_fx_forward_pv_known_value():
    notional, spot, contract_rate, r_d, r_f, t = 1_000_000.0, 5.0, 5.0, 0.10, 0.05, 1.0
    forward = spot * math.exp((r_d - r_f) * t)
    expected = notional * (forward - contract_rate) * math.exp(-r_d * t)
    assert math.isclose(pm.fx_forward_pv(notional, spot, contract_rate, r_d, r_f, t), expected, rel_tol=1e-12)


def test_asian_forward_pv_known_value():
    notional, spot, contract_rate, disc_rate, t = 1000.0, 100.0, 100.0, 0.05, 2.0
    expected_avg = spot * math.exp(disc_rate * (t / 2))
    expected = notional * (expected_avg - contract_rate) * math.exp(-disc_rate * t)
    assert math.isclose(pm.asian_forward_pv(notional, spot, contract_rate, disc_rate, t), expected, rel_tol=1e-12)


# --------------------------------------------------------------------------
# Bond com pré-pagamento, carteira de crédito, NMD, par floater
# --------------------------------------------------------------------------

def test_prepayable_bond_pv_cpr_zero_uses_full_tenor():
    pv = pm.prepayable_bond_pv(face=1000.0, coupon_rate=0.08, tenor_years=10.0, ytm=0.08, spread=0.0, cpr=0.0, vol_juros=0.1)
    assert math.isclose(pv, 1000.0, rel_tol=1e-3)


def test_prepayable_bond_pv_higher_cpr_increases_drag():
    kwargs = dict(face=1000.0, coupon_rate=0.10, tenor_years=15.0, ytm=0.12, spread=0.01, vol_juros=0.2)
    low_cpr = pm.prepayable_bond_pv(cpr=0.05, **kwargs)
    high_cpr = pm.prepayable_bond_pv(cpr=0.30, **kwargs)
    assert low_cpr != high_cpr


def test_credit_portfolio_pv_cpr_zero_uses_full_tenor():
    pv = pm.credit_portfolio_pv(face=1000.0, coupon_rate=0.08, tenor_years=5.0, ytm=0.08, spread=0.0, cpr=0.0, default_rate=0.0)
    assert math.isclose(pv, 1000.0, rel_tol=1e-3)


def test_credit_portfolio_pv_default_rate_reduces_value():
    kwargs = dict(face=1000.0, coupon_rate=0.10, tenor_years=5.0, ytm=0.10, spread=0.0, cpr=0.10)
    no_default = pm.credit_portfolio_pv(default_rate=0.0, **kwargs)
    with_default = pm.credit_portfolio_pv(default_rate=0.05, **kwargs)
    assert with_default < no_default


def test_nmd_liability_pv_zero_decay_rate_edge_case():
    assert pm.nmd_liability_pv(notional=1000.0, curve_rate=0.10, decay_rate=0.0) == 0.0


def test_nmd_liability_pv_base_case():
    pv = pm.nmd_liability_pv(notional=1000.0, curve_rate=0.10, decay_rate=0.20)
    expected = 1000.0 * pm.discount_factor(0.10, 5.0)
    assert math.isclose(pv, expected, rel_tol=1e-9)


def test_par_floater_pv_at_reference_rate_is_par():
    assert math.isclose(pm.par_floater_pv(1000.0, 0.10, 0.10), 1000.0, rel_tol=1e-9)


# --------------------------------------------------------------------------
# Dispatcher price_position / price_portfolio
# --------------------------------------------------------------------------

_MARKET = {
    "di_pre": 0.10, "ipca_real": 0.05, "pre_nominal": 0.11, "ust": 0.045, "sofr": 0.05, "fed_funds": 0.0525,
    "usdbrl": 5.0, "ibov": 125_000.0, "spx": 5_200.0, "soja": 1_350.0, "brent": 82.0, "wti": 78.0,
    "vol_ibov": 0.22, "vol_spx": 0.16, "vol_usdbrl": 0.14, "vol_juros": 0.18,
    "spread_debentures": 0.025, "spread_bonds_corp": 0.018, "nmd_decay_rate": 0.15, "cpr": 0.12,
}


def test_price_position_unknown_pricer_raises():
    bogus = Position(id=999, name="bogus", asset_class="x", currency="BRL", direction=1, notional=100.0, risk_factors=(), pricer="nao_existe")
    with pytest.raises(ValueError):
        pm.price_position(bogus, _MARKET)


def test_price_portfolio_unsupported_currency_raises():
    bogus = Position(id=999, name="bogus", asset_class="x", currency="EUR", direction=1, notional=100.0, risk_factors=("di_pre",), pricer="par_floater", params={"curve": "di_pre", "reference_rate": 0.10})
    with pytest.raises(ValueError):
        pm.price_portfolio([bogus], _MARKET)


def test_price_portfolio_usd_position_requires_usdbrl_in_market():
    usd_position = Position(id=999, name="usd", asset_class="x", currency="USD", direction=1, notional=100.0, risk_factors=("ust",), pricer="fixed_bond", params={"curve": "ust", "coupon": 0.05, "tenor_years": 5, "freq": 2})
    market_no_fx = {k: v for k, v in _MARKET.items() if k != "usdbrl"}
    with pytest.raises(KeyError):
        pm.price_portfolio([usd_position], market_no_fx)


def test_price_portfolio_full_reference_book_runs_without_error():
    from src.portfolio.base_portfolio import POSITIONS

    pvs = pm.price_portfolio(POSITIONS, _MARKET)
    assert set(pvs) == {p.id for p in POSITIONS}
    assert all(isinstance(v, float) for v in pvs.values())


def test_price_position_direction_flips_sign():
    long_pos = Position(id=1, name="x", asset_class="x", currency="BRL", direction=1, notional=1000.0, risk_factors=("di_pre",), pricer="par_floater", params={"curve": "di_pre", "reference_rate": 0.10})
    short_pos = Position(id=2, name="x", asset_class="x", currency="BRL", direction=-1, notional=1000.0, risk_factors=("di_pre",), pricer="par_floater", params={"curve": "di_pre", "reference_rate": 0.10})
    assert pm.price_position(long_pos, _MARKET) == -pm.price_position(short_pos, _MARKET)
