# data/pricing_models/

Por CLAUDE.md §7, este diretório existe para os "modelos de precificação por
instrumento", congelados junto com `data/risk_factors/`.

Na prática, os modelos de precificação (Black-Scholes/Garman-Kohlhagen,
binomial americano, bond pricing, collar swap, forwards, etc.) são fórmulas
determinísticas, não dados tabulares — por isso vivem como código versionado
em `src/portfolio/pricing_models.py`, não como CSVs aqui. Isso já satisfaz a
regra de imutabilidade do §5.3 (código commitado em Git só muda por commit
deliberado, nunca como efeito colateral de rodar o pipeline).

Este diretório fica reservado, conforme a estrutura prescrita, para eventuais
artefatos gerados a partir desses modelos que precisem ser congelados como
dado (ex.: uma tabela de preços de referência pré-calculados para um snapshot
específico da carteira base, se algum teste de integração vier a precisar
disso) — nenhum artefato desse tipo existe ainda.
