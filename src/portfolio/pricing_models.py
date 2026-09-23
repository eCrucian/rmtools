"""Modelos de precificação por instrumento (CLAUDE.md §5.3 — `pricing_models.py`).

Este é um portfólio de REFERÊNCIA para testar o pipeline de validação (stability
tests, backtest), não uma biblioteca de precificação de produção. Cada pricer
usa a forma fechada/numérica padrão mais simples que ainda captura a
sensibilidade correta aos fatores de risco listados em §5.2 — simplificações
deliberadas estão documentadas em cada função.

Convenções:
- `MarketSnapshot` é um dict {nome_do_fator: valor} para uma data específica
  (uma linha dos CSVs congelados em data/risk_factors/, nunca gerado aqui).
- Toda `pricer(position, market) -> float` devolve o PV na moeda nativa da
  posição (`position.currency`); `price_portfolio` converte para BRL.
- Taxas são anuais, compostas anualmente: DF(t) = (1+r)^-t, salvo onde anotado.
- scipy é opcional (fallback em `_stats.py`, CLAUDE.md §2.2).
"""

from __future__ import annotations

import math
from typing import Callable

from ._stats import norm_cdf

MarketSnapshot = dict[str, float]


# --------------------------------------------------------------------------
# Helpers de desconto / renda fixa
# --------------------------------------------------------------------------

def discount_factor(rate: float, t: float, freq: int = 1) -> float:
    if t <= 0:
        return 1.0
    return (1.0 + rate / freq) ** (-freq * t)


def annuity_factor(rate: float, tenor_years: float) -> float:
    """Fator de anuidade anual — usado como proxy de duration em swaps/futuros
    simplificados (sem termo estrutura completa, §5.3 nota de simplificação)."""
    if abs(rate) < 1e-8:
        return tenor_years
    return (1.0 - (1.0 + rate) ** (-tenor_years)) / rate


def fixed_bond_pv(face: float, coupon_rate: float, tenor_years: float, freq: int, ytm: float) -> float:
    n_periods = max(int(round(tenor_years * freq)), 0)
    if n_periods == 0:
        return face
    coupon = face * coupon_rate / freq
    pv = sum(coupon * discount_factor(ytm, k / freq, freq=freq) for k in range(1, n_periods + 1))
    pv += face * discount_factor(ytm, tenor_years, freq=freq)
    return pv


def zero_bond_pv(face: float, tenor_years: float, ytm: float) -> float:
    return face * discount_factor(ytm, tenor_years, freq=1)


# --------------------------------------------------------------------------
# Opções — Black-Scholes / Garman-Kohlhagen / binomial americano
# --------------------------------------------------------------------------

def _d1_d2(spot: float, strike: float, rate: float, vol: float, t: float, carry: float = 0.0) -> tuple[float, float]:
    if t <= 0 or vol <= 0:
        raise ValueError("tenor e vol devem ser positivos para precificar uma opção")
    d1 = (math.log(spot / strike) + (rate - carry + 0.5 * vol * vol) * t) / (vol * math.sqrt(t))
    d2 = d1 - vol * math.sqrt(t)
    return d1, d2


def black_scholes(spot: float, strike: float, rate: float, vol: float, t: float, option_type: str, carry: float = 0.0) -> float:
    """Black-Scholes com custo de carrego `carry` (0 = ação sem dividendo;
    `carry = rate_domestic - rate_foreign` reproduz Garman-Kohlhagen para FX)."""
    d1, d2 = _d1_d2(spot, strike, rate, vol, t, carry)
    disc_r = math.exp(-rate * t)
    disc_carry = math.exp(-carry * t)
    if option_type == "call":
        return spot * disc_carry * norm_cdf(d1) - strike * disc_r * norm_cdf(d2)
    if option_type == "put":
        return strike * disc_r * norm_cdf(-d2) - spot * disc_carry * norm_cdf(-d1)
    raise ValueError(f"option_type inválido: {option_type!r} (esperado 'call' ou 'put')")


def binomial_american(
    spot: float, strike: float, rate: float, vol: float, t: float, option_type: str, steps: int = 40, carry: float = 0.0
) -> float:
    """Árvore binomial CRR com exercício antecipado a cada nó — prêmio de
    exercício americano (§5.1, instrumentos 9/11/13)."""
    if t <= 0 or vol <= 0:
        raise ValueError("tenor e vol devem ser positivos para precificar uma opção")
    if steps < 1:
        raise ValueError("steps deve ser >= 1")

    dt = t / steps
    u = math.exp(vol * math.sqrt(dt))
    d = 1.0 / u
    disc = math.exp(-rate * dt)
    p = (math.exp((rate - carry) * dt) - d) / (u - d)
    if not (0.0 <= p <= 1.0):
        raise ValueError("parâmetros geram probabilidade neutra ao risco inválida (dt grande demais / vol baixa demais)")

    prices = [spot * u**j * d**(steps - j) for j in range(steps + 1)]
    if option_type == "call":
        values = [max(px - strike, 0.0) for px in prices]
    elif option_type == "put":
        values = [max(strike - px, 0.0) for px in prices]
    else:
        raise ValueError(f"option_type inválido: {option_type!r} (esperado 'call' ou 'put')")

    for step in range(steps - 1, -1, -1):
        new_prices = [spot * u**j * d**(step - j) for j in range(step + 1)]
        new_values = []
        for j in range(step + 1):
            continuation = disc * (p * values[j + 1] + (1 - p) * values[j])
            exercise = max(new_prices[j] - strike, 0.0) if option_type == "call" else max(strike - new_prices[j], 0.0)
            new_values.append(max(continuation, exercise))
        values = new_values
    return values[0]


def quanto_option(
    spot: float, strike: float, rate_domestic: float, vol: float, fx_vol: float, correlation: float, t: float, option_type: str
) -> float:
    """Opção quanto (§5.1, instrumento 24): ajusta o drift do ativo subjacente
    pelo termo de correção quanto -correlation*vol*fx_vol e desconta/paga no
    câmbio fixo contratual (o payoff já está numa moeda, só o drift é ajustado
    — forma padrão de quanto option sob Black-Scholes)."""
    quanto_carry = rate_domestic + correlation * vol * fx_vol
    return black_scholes(spot, strike, rate_domestic, vol, t, option_type, carry=quanto_carry)


# --------------------------------------------------------------------------
# Swap com limitador (collar): swap vanilla (via annuity_factor) + cap - floor
# precificados com Black-76 sobre a curva de referência.
# --------------------------------------------------------------------------

def black76_cap_floor(forward_rate: float, strike_rate: float, vol: float, t: float, notional: float, kind: str) -> float:
    if forward_rate <= 0 or strike_rate <= 0:
        # aproximação Black-76 exige taxa positiva no log; fora desse regime,
        # o valor intrínseco descontado é a melhor aproximação disponível.
        intrinsic = max(forward_rate - strike_rate, 0.0) if kind == "cap" else max(strike_rate - forward_rate, 0.0)
        return notional * intrinsic * math.exp(-forward_rate * t)
    d1, d2 = _d1_d2(forward_rate, strike_rate, 0.0, vol, t)
    disc = math.exp(-forward_rate * t)
    if kind == "cap":
        return notional * disc * (forward_rate * norm_cdf(d1) - strike_rate * norm_cdf(d2))
    if kind == "floor":
        return notional * disc * (strike_rate * norm_cdf(-d2) - forward_rate * norm_cdf(-d1))
    raise ValueError(f"kind inválido: {kind!r} (esperado 'cap' ou 'floor')")


def collar_swap(
    notional: float,
    pay_rate: float,
    receive_rate: float,
    cap_rate: float,
    floor_rate: float,
    vol: float,
    tenor_years: float,
) -> float:
    """PV = swap vanilla (recebe `receive_rate`, paga `pay_rate`) + cap sobre a
    perna paga - floor sobre a perna recebida (collar payer simplificado,
    §5.1 instrumentos 14-16). Termo estrutura reduzida a um fator de anuidade
    sobre `receive_rate` (simplificação documentada em §5.3)."""
    annuity = annuity_factor(receive_rate, tenor_years)
    vanilla_pv = notional * (receive_rate - pay_rate) * annuity
    cap_pv = black76_cap_floor(pay_rate, cap_rate, vol, tenor_years, notional, "cap")
    floor_pv = black76_cap_floor(receive_rate, floor_rate, vol, tenor_years, notional, "floor")
    return vanilla_pv + cap_pv - floor_pv


# --------------------------------------------------------------------------
# Futuros / a termo (FX e taxa)
# --------------------------------------------------------------------------

def rate_future_pv(notional: float, curve_rate: float, reference_rate: float, dv01_years: float) -> float:
    """P&L linearizado de um futuro de taxa (Fed Funds/Treasury, §5.1
    instrumentos 17-18) em torno de uma taxa de referência contratual:
    PV ≈ -notional * dv01_years * (curve_rate - reference_rate)."""
    return -notional * dv01_years * (curve_rate - reference_rate)


def fx_forward_pv(notional_foreign: float, spot: float, contract_rate: float, domestic_rate: float, foreign_rate: float, t: float) -> float:
    """NDF/futuro de dólar (§5.1 instrumentos 19-20): PV em moeda doméstica
    (BRL) de um contrato a termo via paridade coberta de juros."""
    forward_rate = spot * math.exp((domestic_rate - foreign_rate) * t)
    return notional_foreign * (forward_rate - contract_rate) * math.exp(-domestic_rate * t)


def asian_forward_pv(notional: float, spot: float, contract_rate: float, discount_rate: float, tenor_years: float) -> float:
    """NDF asiática/average-rate (§5.1 instrumentos 21-22): payoff linear sobre
    o preço médio esperado no período de apuração — sem opcionalidade, então
    só o primeiro momento da GBM importa. Aproxima E[avg(S)] pelo crescimento
    até o ponto médio da janela de apuração (aproximação padrão para forwards
    de preço médio, §5.3 simplificação documentada)."""
    expected_avg = spot * math.exp(discount_rate * (tenor_years / 2.0))
    return notional * (expected_avg - contract_rate) * math.exp(-discount_rate * tenor_years)


# --------------------------------------------------------------------------
# Bond com pré-pagamento (MBS-like) e carteira de crédito
# --------------------------------------------------------------------------

def prepayable_bond_pv(
    face: float, coupon_rate: float, tenor_years: float, ytm: float, spread: float, cpr: float, vol_juros: float
) -> float:
    """Bond amortizável com pré-pagamento (§5.1 instrumento 23): desconta um
    fluxo esperado que amortiza mais rápido quanto maior o CPR (vida média
    efetiva = 1/cpr, truncada no tenor contratual), e subtrai um ajuste de
    convexidade negativa proporcional a vol_juros (proxy do valor da opção de
    pré-pagamento embutida — simplificação documentada, não um modelo OAS
    completo)."""
    effective_life = min(1.0 / cpr, tenor_years) if cpr > 0 else tenor_years
    y = ytm + spread
    base_pv = fixed_bond_pv(face, coupon_rate, effective_life, freq=2, ytm=y)
    # A opção de pré-pagamento só tem valor quando o CPR de fato acelera a
    # amortização (effective_life < tenor_years); em cpr=0 (ou cpr baixo o
    # bastante para o teto no tenor contratual) o drag é zero por construção.
    acceleration = 1.0 - effective_life / max(tenor_years, 1e-6)
    prepayment_option_drag = face * vol_juros * acceleration * 0.50
    return base_pv - prepayment_option_drag


def credit_portfolio_pv(
    face: float, coupon_rate: float, tenor_years: float, ytm: float, spread: float, cpr: float, default_rate: float
) -> float:
    """Carteira de crédito com pré-pagamento (§5.1 instrumento 26): mesma
    lógica de vida efetiva do CPR do instrumento 23, com uma perda esperada
    adicional por inadimplência. `default_rate` é tratado como parâmetro fixo
    do instrumento (não um fator de risco estocástico — §5.2 só lista
    nmd_decay_rate/cpr como fatores comportamentais; taxa de inadimplência é
    uma premissa fixa documentada aqui, simplificação deliberada)."""
    effective_life = min(1.0 / cpr, tenor_years) if cpr > 0 else tenor_years
    y = ytm + spread
    base_pv = fixed_bond_pv(face, coupon_rate, effective_life, freq=2, ytm=y)
    expected_loss = face * default_rate * effective_life
    return base_pv - expected_loss


def nmd_liability_pv(notional: float, curve_rate: float, decay_rate: float) -> float:
    """NMD (§5.1 instrumento 25): passivo bancário sem vencimento contratual,
    valorizado como um zero-coupon equivalente com vida efetiva = 1/decay_rate
    (maior decaimento => menor duration => menor sensibilidade a juros —
    modelo comportamental simplificado padrão para pré-teste de IRRBB)."""
    # decay_rate -> 0 significa que o depósito nunca decai (vida comportamental
    # infinita), então o "zero-coupon equivalente" deve ser descontado até o
    # infinito (PV -> 0) — não confundir com vida zero (que daria PV = notional
    # à vista, o oposto do comportamento pretendido).
    effective_life = 1.0 / decay_rate if decay_rate > 0 else math.inf
    return notional * discount_factor(curve_rate, effective_life, freq=1)


def par_floater_pv(notional: float, curve_rate: float, reference_rate: float, residual_duration: float = 0.05) -> float:
    """Pós-fixado quase-par (LFT, §5.1 instrumento 1): resíduo de convexidade
    pequeno em torno do par, sensível ao spread entre a taxa corrente e uma
    taxa de referência contratual (simplificação — não é um floater exato)."""
    return notional * math.exp(-residual_duration * (curve_rate - reference_rate))


# --------------------------------------------------------------------------
# Dispatcher: Position (base_portfolio.py) + MarketSnapshot -> PV
# --------------------------------------------------------------------------

def _price_par_floater(notional: float, params: dict, market: MarketSnapshot) -> float:
    return par_floater_pv(
        notional, market[params["curve"]], params["reference_rate"], params.get("residual_duration", 0.05)
    )


def _price_fixed_bond(notional: float, params: dict, market: MarketSnapshot) -> float:
    return fixed_bond_pv(notional, params["coupon"], params["tenor_years"], params["freq"], market[params["curve"]])


def _price_zero_bond(notional: float, params: dict, market: MarketSnapshot) -> float:
    return zero_bond_pv(notional, params["tenor_years"], market[params["curve"]])


def _price_credit_bond(notional: float, params: dict, market: MarketSnapshot) -> float:
    ytm = market[params["curve"]] + market[params["spread_curve"]]
    return fixed_bond_pv(notional, params["coupon"], params["tenor_years"], params["freq"], ytm)


def _price_black_scholes(notional: float, params: dict, market: MarketSnapshot) -> float:
    return notional * black_scholes(
        market[params["underlying"]], params["strike"], market[params["rate"]], market[params["vol"]],
        params["tenor_years"], params["option_type"],
    )


def _price_binomial_american(notional: float, params: dict, market: MarketSnapshot) -> float:
    return notional * binomial_american(
        market[params["underlying"]], params["strike"], market[params["rate"]], market[params["vol"]],
        params["tenor_years"], params["option_type"], params.get("steps", 40),
    )


def _price_fx_black_scholes(notional: float, params: dict, market: MarketSnapshot) -> float:
    r_d, r_f = market[params["rate_domestic"]], market[params["rate_foreign"]]
    return notional * black_scholes(
        market[params["underlying"]], params["strike"], r_d, market[params["vol"]],
        params["tenor_years"], params["option_type"], carry=r_d - r_f,
    )


def _price_fx_binomial_american(notional: float, params: dict, market: MarketSnapshot) -> float:
    r_d, r_f = market[params["rate_domestic"]], market[params["rate_foreign"]]
    return notional * binomial_american(
        market[params["underlying"]], params["strike"], r_d, market[params["vol"]],
        params["tenor_years"], params["option_type"], params.get("steps", 40), carry=r_d - r_f,
    )


def _price_collar_swap(notional: float, params: dict, market: MarketSnapshot) -> float:
    return collar_swap(
        notional, market[params["pay_curve"]], market[params["receive_curve"]],
        params["cap_rate"], params["floor_rate"], market[params["vol"]], params["tenor_years"],
    )


def _price_rate_future(notional: float, params: dict, market: MarketSnapshot) -> float:
    return rate_future_pv(notional, market[params["curve"]], params["reference_rate"], params["dv01_years"])


def _price_fx_forward(notional: float, params: dict, market: MarketSnapshot) -> float:
    return fx_forward_pv(
        notional, market[params["spot"]], params["contract_rate"],
        market[params["domestic_curve"]], market[params["foreign_curve"]], params["tenor_years"],
    )


def _price_asian_forward(notional: float, params: dict, market: MarketSnapshot) -> float:
    return asian_forward_pv(
        notional, market[params["spot"]], params["contract_rate"], market[params["discount_curve"]], params["tenor_years"]
    )


def _price_prepayable_bond(notional: float, params: dict, market: MarketSnapshot) -> float:
    return prepayable_bond_pv(
        notional, params["coupon"], params["tenor_years"], market[params["curve"]],
        market[params["spread_curve"]], market[params["cpr_factor"]], market[params["vol_curve"]],
    )


def _price_quanto_option(notional: float, params: dict, market: MarketSnapshot) -> float:
    return notional * quanto_option(
        market[params["underlying"]], params["strike"], market[params["rate_domestic"]],
        market[params["vol"]], market[params["fx_vol"]], params["correlation"],
        params["tenor_years"], params["option_type"],
    )


def _price_nmd_liability(notional: float, params: dict, market: MarketSnapshot) -> float:
    return nmd_liability_pv(notional, market[params["curve"]], market[params["decay_factor"]])


def _price_credit_portfolio(notional: float, params: dict, market: MarketSnapshot) -> float:
    return credit_portfolio_pv(
        notional, params["coupon"], params["tenor_years"], market[params["curve"]],
        market[params["spread_curve"]], market[params["cpr_factor"]], params["default_rate"],
    )


PRICERS: dict[str, Callable[[float, dict, MarketSnapshot], float]] = {
    "par_floater": _price_par_floater,
    "fixed_bond": _price_fixed_bond,
    "zero_bond": _price_zero_bond,
    "credit_bond": _price_credit_bond,
    "black_scholes": _price_black_scholes,
    "binomial_american": _price_binomial_american,
    "fx_black_scholes": _price_fx_black_scholes,
    "fx_binomial_american": _price_fx_binomial_american,
    "collar_swap": _price_collar_swap,
    "rate_future": _price_rate_future,
    "fx_forward": _price_fx_forward,
    "asian_forward": _price_asian_forward,
    "prepayable_bond": _price_prepayable_bond,
    "quanto_option": _price_quanto_option,
    "nmd_liability": _price_nmd_liability,
    "credit_portfolio": _price_credit_portfolio,
}


def price_position(position, market: MarketSnapshot) -> float:
    """PV de uma `Position` (base_portfolio.py) na moeda nativa dela, já com o
    sinal de `direction` aplicado (comprado/ativo=+1, vendido/passivo=-1)."""
    pricer = PRICERS.get(position.pricer)
    if pricer is None:
        raise ValueError(f"pricer desconhecido: {position.pricer!r} (posição {position.id} — {position.name})")
    return position.direction * pricer(position.notional, position.params, market)


def price_portfolio(positions, market: MarketSnapshot) -> dict[int, float]:
    """PV de cada posição convertido para BRL (moeda de consolidação da
    carteira hipotética). Posições em USD usam market['usdbrl'] no spot da
    data do snapshot."""
    usdbrl = market.get("usdbrl")
    result: dict[int, float] = {}
    for position in positions:
        pv_native = price_position(position, market)
        if position.currency == "USD":
            if usdbrl is None:
                raise KeyError("market snapshot não tem 'usdbrl' — necessário para converter posições em USD")
            result[position.id] = pv_native * usdbrl
        elif position.currency == "BRL":
            result[position.id] = pv_native
        else:
            raise ValueError(f"moeda não suportada: {position.currency!r} (posição {position.id})")
    return result
