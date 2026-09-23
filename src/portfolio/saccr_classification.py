"""Classificação das 26 posições da carteira base (§5.1) nas 5 classes de
ativo do SA-CCR (BCBS d279): interest_rate, fx, credit, equity, commodity.

Convenção própria deste repositório (não uma tabela oficial transcrita) —
cross-currency swaps e opções quanto, que o SA-CCR de fato trataria com
componentes em mais de uma classe, são simplificados aqui para uma única
classe dominante (documentado, não escondido). Usada só para alimentar o
campo `asset_class_saccr` no snapshot de posições passado a `compute()`
(§Action 06) — nunca para calcular Add-On dentro do pipeline em si, que é
responsabilidade exclusiva do código gerado a partir da especificação da doc.
"""

from __future__ import annotations

SACCR_ASSET_CLASS: dict[int, str] = {
    1: "interest_rate",   # LFT
    2: "interest_rate",   # NTN-B
    3: "interest_rate",   # NTN-F
    4: "interest_rate",   # LTN
    5: "credit",          # Debêntures
    6: "credit",          # Bonds corporativos USD
    7: "interest_rate",   # US Treasuries
    8: "equity",          # Opção IBOV europeia
    9: "equity",          # Opção IBOV americana
    10: "equity",         # Opção SPX europeia
    11: "equity",         # Opção SPX americana
    12: "fx",             # Opção USD/BRL europeia
    13: "fx",             # Opção USD/BRL americana
    14: "interest_rate",  # Swap collar CDI x Pré
    15: "interest_rate",  # Swap collar IPCA x Pré
    16: "interest_rate",  # Swap collar USD x SOFR (simplificação: componente FX ignorado)
    17: "interest_rate",  # Futuro Fed Funds
    18: "interest_rate",  # Futuro Treasury
    19: "fx",             # Futuro de Dólar
    20: "fx",             # NDF de dólar
    21: "commodity",      # NDF soja
    22: "commodity",      # NDF petróleo
    23: "interest_rate",  # Bond com pré-pagamento
    24: "equity",         # Opção quanto SPX (simplificação: componente FX ignorado)
    25: "interest_rate",  # NMD
    26: "credit",         # Carteira de crédito
}
