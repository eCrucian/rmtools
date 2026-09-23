def compute(portfolio: dict, risk_factors: dict, params: dict) -> dict:
    alpha = params["alpha"]
    SF_fx = params["SF_fx"]
    
    def _effective_notional(i):
        notional = portfolio["positions"][i]["notional"]
        delta = portfolio["positions"][i]["direction"]
        M_i = (portfolio["positions"][i]["maturity_years"] if portfolio["positions"][i]["maturity_years"] is not None else 0)
        MF_i = (M_i ** 0.5) if M_i >= 0 else 0
        return notional * delta * MF_i
    
    def _sum_effective_notional():
        total = 0
        for i in range(len(portfolio["positions"])):
            total += _effective_notional(i)
        return abs(total)
    
    def _add_on():
        return SF_fx * _sum_effective_notional()
    
    def _replacement_cost():
        V = portfolio["value"]
        C = 0  # Colateral líquido recebido não fornecido
        return max(V - C, 0)
    
    def _multiplicador():
        V = portfolio["value"]
        C = 0  # Colateral líquido recebido não fornecido
        AddOn = _add_on()
        if (V - C) >= 0:
            return 1
        else:
            return min(1, 0.05 + 0.95 * exp((V - C) / (2 * 0.95 * AddOn)))
    
    def _pfe():
        multiplicador = _multiplicador()
        AddOn = _add_on()
        return multiplicador * AddOn
    
    def _ead():
        RC = _replacement_cost()
        PFE = _pfe()
        return alpha * (RC + PFE)
    
    return {"valor": _ead()}