# Metodologia — Exposição Potencial Futura via SA-CCR (Standardised Approach for Counterparty Credit Risk)

## 1. Escopo de aplicação

Este documento descreve o cálculo do Exposure at Default (EAD) de risco de
crédito de contraparte para os derivativos de câmbio (termos/NDFs) da mesa de
tesouraria, sujeitos ao SA-CCR (BCBS d279, "The standardised approach for
measuring counterparty credit risk exposures", 2014).

**Escopo desta versão (simplificação deliberada — ver §6):** cobre um único
netting set, com transações de uma única classe de ativo (Câmbio) e uma
única hedging set (mesmo par de moedas), sem acordo de margem (CSA). A
extensão para múltiplas classes de ativo (Juros, Crédito, Ações,
Commodities) e para netting sets margeados segue a mesma estrutura de
cálculo (§2-§4), acrescida da soma entre classes (§6) e do ajuste de
threshold/MTA/NICA para CSA — não coberta nesta versão.

## 2. Proposta do modelo — visão geral

```
EAD = alpha * (RC + PFE)
```

com `alpha = 1,4` (fator regulatório fixo, BCBS d279 §130), `RC` o
Replacement Cost e `PFE` a Potential Future Exposure.

## 3. Replacement Cost (RC)

Netting set não-margeado (sem CSA — escopo desta versão):

```
RC = max(V - C, 0)
```

`V` é o valor de mercado líquido do netting set (soma do MTM de todas as
transações); `C` é o colateral líquido recebido (sempre 0 nesta versão).

## 4. Potential Future Exposure (PFE)

```
PFE = multiplicador * AddOn
```

### 4.1 Multiplicador

```
multiplicador = 1,                                                     se (V - C) >= 0
multiplicador = min(1; 0,05 + 0,95 * exp((V - C) / (2 * 0,95 * AddOn))), se (V - C) < 0
```

### 4.2 Add-On da hedging set

Uma única hedging set nesta versão (todas as transações são câmbio, mesmo
par de moedas):

```
AddOn = SF_fx * |soma_i EffectiveNotional_i|
```

com `SF_fx = 4,00%` (fator de supervisão para Câmbio, BCBS d279 Tabela 2).

### 4.3 Notional efetivo por transação

```
EffectiveNotional_i = notional_i * delta_i * MF_i
MF_i = sqrt(min(M_i, 1))
```

`notional_i` é o notional da transação `i`; `delta_i` é +1 para posição
compradora e -1 para vendedora; `M_i` é o prazo remanescente até o
vencimento, em anos; `MF_i` é o fator de maturidade (netting set
não-margeado — sem ajuste por período de risco de margem).

## 5. Hipóteses

- **H1 (MTM corrente é representativo)**: `V` (soma dos MTM correntes) é
  assumido como uma estimativa não-viesada do valor de mercado no momento do
  cálculo — depende da qualidade da curva de marcação usada a montante
  (fora do escopo deste documento).
- **H2 (ausência de wrong-way risk material)**: o modelo não ajusta EAD para
  correlação adversa entre a qualidade de crédito da contraparte e a
  exposição. Não testada quantitativamente nesta versão (exigiria dados de
  CDS/probabilidade de default da contraparte, não disponíveis nesta base).
- **H3 (uma única hedging set é suficiente para o netting set)**: assume-se
  que todas as transações do netting set pertencem à mesma classe de ativo e
  par de moedas — ver §6 para a extensão necessária quando isso não vale.

## 6. Limitações

- **Uma única classe de ativo (Câmbio) e uma única hedging set** — a
  extensão para múltiplas classes soma o Add-On de cada classe/hedging set
  (`AddOn_total = soma sobre classes de AddOn_classe`, sem benefício de
  diversificação entre classes, BCBS d279 §157) e, para Juros/Crédito,
  substitui `EffectiveNotional_i` por uma versão que usa a duração
  supervisionada (`SD_i`) em vez do notional bruto — não implementada aqui.
- **Netting sets margeados (CSA) não são suportados** — exigem threshold
  (TH), minimum transfer amount (MTA), net independent collateral amount
  (NICA) e ajuste do fator de maturidade pelo período de risco de margem
  (MPOR).
- **Wrong-way risk específico** (H2) não é capturado.
- O modelo não ajusta `delta_i` para opções (delta de Black-Scholes) — só
  cobre instrumentos lineares (termos/NDFs), consistente com o escopo
  declarado em §1.

## 7. Motivação do modelo

O SA-CCR (BCBS d279, 2014) substituiu o Current Exposure Method (CEM) por
ser mais sensível a risco: reconhece parcialmente benefícios de hedge dentro
de uma hedging set via `|soma_i EffectiveNotional_i|` (em vez de somar
valores absolutos, que ignoraria posições compensatórias), e diferencia o
fator de maturidade por transação em vez de um add-on fixo por tipo de
produto. A adoção é também exigida regulatoriamente (Basileia III) para
bancos que apuram capital de risco de crédito de contraparte pela abordagem
padronizada.

## 8. Exemplo de cálculo

Um netting set com três transações de câmbio (sem CSA) está anexado em
`exemplo_calculado.csv`, com os valores intermediários (fator de
maturidade, notional efetivo, Add-On) e o resultado final (RC, PFE, EAD)
calculados a partir das fórmulas acima.
