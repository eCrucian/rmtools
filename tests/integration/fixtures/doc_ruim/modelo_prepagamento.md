# Modelo Interno — Ajuste de Pré-pagamento

Aplica-se a derivativos e outros instrumentos da carteira que possuem
comportamento de pré-pagamento.

O valor ajustado é dado por:

VA = V0 * (1 - CPR)^T

Onde V0 é o valor de referência, CPR é a taxa de pré-pagamento e T é o prazo.
A curva de funding usada no cálculo é a curva interna da mesa.

O modelo é calibrado periodicamente pela área de risco com base em dados
históricos observados da carteira.

## Observações

O resultado deve ser reportado mensalmente ao comitê de risco.
