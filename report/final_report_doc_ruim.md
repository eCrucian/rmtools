# Relatório de Validação Independente — run `doc_ruim`

## 1. Sumário executivo

Run `doc_ruim` — status geral: **concluído com pendências (needs_human_review — ver seção 10)**. Nota de qualidade documental agregada: **1.57**. 0 resultado(s) de backtest, 0 resultado(s) de estabilidade registrados nesta run. Ver seções seguintes para detalhe por métrica.

## 2. Escopo e metodologia da validação

- **run_id**: `doc_ruim`
- **Documento de origem**: ['tests/integration/fixtures/doc_ruim/modelo_prepagamento.md']
- **Backend de LLM**: ollama
- **Iniciada em**: 2026-09-23T00:40:31.822102+00:00
- **Finalizada em**: em andamento

## 3. Avaliação da qualidade da documentação

| Item | Nota (0-4) | Evidência |
| --- | --- | --- |
| escopo_de_aplicacao | 3 | O texto menciona que o modelo se aplica a derivativos e outros instrumentos da carteira que possuem comportamento de pré-pagamento. |
| proposta_do_modelo | 3 | O texto descreve a fórmula VA = V0 * (1 - CPR)^T e explica o cálculo do valor ajustado. |
| desenvolvimento_metodologico | 2 | O texto menciona a curva de funding usada no cálculo, mas não descreve detalhadamente o processo de calibração ou os métodos utilizados. |
| declaracao_e_teste_de_hipoteses | 1 | O texto não menciona hipóteses testadas ou verificações realizadas para validar o modelo. |
| limitacoes | 1 | O texto não menciona limitações ou restrições do modelo ou suas condições de aplicação. |
| motivacao_do_modelo | 1 | O texto não explica a motivação ou a razão para a criação do modelo. |
| codigo_exemplo_anexo | 0 | O texto não inclui nenhum código exemplo anexo ou referência a código de exemplo. |

## 4. Avaliação da qualidade metodológica

### Hipóteses avaliadas

| Hipótese | Testável? | Justificativa |
| --- | --- | --- |
| O modelo é aplicado a derivativos e outros instrumentos da carteira que possuem comportamento de pré-pagamento | True | A hipótese pode ser testada quantitativamente ao verificar se os instrumentos identificados na carteira (derivativos e outros) realmente apresentam comportamento de pré-pagamento, com base em dados históricos ou simulações. |
| A curva de funding usada no cálculo é a curva interna da mesa | True | A hipótese pode ser testada quantitativamente ao comparar a curva de funding utilizada no modelo com a curva interna da mesa, verificando se há consistência entre os valores e a metodologia de cálculo. |

### Limitações discutidas

- A hipótese de que a curva de funding é a curva interna da mesa pode não ser válida em todos os cenários, especialmente em mercados voláteis ou em situações de crise financeira.
- A aplicação do modelo a derivativos e outros instrumentos da carteira que possuem comportamento de pré-pagamento pode não ser adequada se os instrumentos não forem realmente sujeitos a pré-pagamento.

### Referências citadas

| Referência | Não verificada? |
| --- | --- |
| BCBS 239 | True |
| Jorion, P. (2006). Value at Risk: The New Benchmark for Managing Financial Risk. | True |

## 5. Aderência normativa

_(não aplicável — Action 05 skipped ou não rodou nesta run; ver seção 8.)_

## 6. Testes de estabilidade

_(nenhum registro)_

_(gráfico de elasticidade não gerado nesta run — sem resultados de estabilidade com choque isolado.)_

## 7. Backtesting

_(nenhum registro)_

_(gráfico de exceções não gerado nesta run — sem resultado de backtest para holding period=1.)_

## 8. Replicabilidade

### (a) Lacunas da documentação (decisions_log)

### Criticidade: alta (0)

_(nenhuma)_

### Criticidade: media (1)

| Action | Campo | Ambiguidade | Decisão tomada | Fonte |
| --- | --- | --- | --- | --- |
| 06_generate_reference_code | Valor Ajustado para Pré-pagamento.codigo_gerado.tentativa_5 | N/A — tentativa de geração de código rejeitada pelo sandbox. | Tentativa 5/5 rejeitada: exit code != 0 | assunção conservadora |

### Criticidade: baixa (4)

| Action | Campo | Ambiguidade | Decisão tomada | Fonte |
| --- | --- | --- | --- | --- |
| 06_generate_reference_code | Valor Ajustado para Pré-pagamento.codigo_gerado.tentativa_1 | N/A — tentativa de geração de código rejeitada pelo sandbox. | Tentativa 1/5 rejeitada: exit code != 0 | assunção conservadora |
| 06_generate_reference_code | Valor Ajustado para Pré-pagamento.codigo_gerado.tentativa_2 | N/A — tentativa de geração de código rejeitada pelo sandbox. | Tentativa 2/5 rejeitada: exit code != 0 | assunção conservadora |
| 06_generate_reference_code | Valor Ajustado para Pré-pagamento.codigo_gerado.tentativa_3 | N/A — tentativa de geração de código rejeitada pelo sandbox. | Tentativa 3/5 rejeitada: exit code != 0 | assunção conservadora |
| 06_generate_reference_code | Valor Ajustado para Pré-pagamento.codigo_gerado.tentativa_4 | N/A — tentativa de geração de código rejeitada pelo sandbox. | Tentativa 4/5 rejeitada: exit code != 0 | assunção conservadora |

### Esteira de testes extensível

- Executados: 2
- Pendentes/planejados: 0 (nenhum)

## 9. Conclusões e recomendações

### Fragilidades

_(nenhuma fragilidade de criticidade alta registrada nesta run)_

### Sugestões (nice to have)

- Valor Ajustado para Pré-pagamento.codigo_gerado.tentativa_1 (06_generate_reference_code): N/A — tentativa de geração de código rejeitada pelo sandbox.
- Valor Ajustado para Pré-pagamento.codigo_gerado.tentativa_2 (06_generate_reference_code): N/A — tentativa de geração de código rejeitada pelo sandbox.
- Valor Ajustado para Pré-pagamento.codigo_gerado.tentativa_3 (06_generate_reference_code): N/A — tentativa de geração de código rejeitada pelo sandbox.
- Valor Ajustado para Pré-pagamento.codigo_gerado.tentativa_4 (06_generate_reference_code): N/A — tentativa de geração de código rejeitada pelo sandbox.
- Valor Ajustado para Pré-pagamento.codigo_gerado.tentativa_5 (06_generate_reference_code): N/A — tentativa de geração de código rejeitada pelo sandbox.

## 10. Anexos

### Status por action nesta run

| Action | Status | Notas |
| --- | --- | --- |
| 01_ingest_documentation | success | - |
| 02_extract_model_spec | success | 1 métrica(s) extraída(s). |
| 03_assess_doc_quality | success | nota agregada (recalculada a partir dos itens): 1.57; LLM reportou nota_agregada=2.29, divergente da média real dos itens (1.57) — usado o valor recalculado. |
| 04_assess_methodology | success | Nenhuma hipótese declarada mapeou para um teste quantitativo implementado (normalidade/i.i.d./estacionariedade) — nenhum teste rodado nesta run.; referência não verificada: BCBS 239; referência não verificada: Jorion, P. (2006). Value at Risk: The New Benchmark for Managing Financial Risk. |
| 05_regulatory_adherence | skipped | Nenhuma métrica extraída foi classificada como padronizado/regulatório. |
| 06_generate_reference_code | needs_human_review | 0/1 métrica(s) geradas e aceitas em sandbox.; Pendentes: Valor Ajustado para Pré-pagamento (exit code != 0) |
| 07_stability_tests | skipped | Nenhum módulo de métrica disponível (Action 06) — testes de estabilidade não aplicáveis. |
| 08_backtesting | skipped | Nenhum módulo de métrica disponível (Action 06) — backtesting não aplicável. |
| 09_extended_test_suite | success | 2 teste(s) executado(s), 0 pendente(s)/planejado(s). |

### JSONs de teste individuais

_(nenhum teste individual de estabilidade/backtest foi registrado nesta run — ver status das Actions 06/07/08 acima e seção 8 para o motivo.)_
