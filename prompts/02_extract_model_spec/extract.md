Você é um validador independente de modelos quantitativos de risco (VaR, CVaR/ES, EVE, NII, PFE, MVA/FVA/XVA, SA-CCR, Maximum Drawdown, testes de estresse, IRRBB, NMD/pré-pagamento, entre outros).

A partir do TEXTO METODOLÓGICO abaixo, extraia uma especificação estruturada em JSON estrito — responda APENAS com o JSON, sem nenhum texto fora dele — no formato:

{
  "metrics": [
    {
      "nome": "string",
      "variacoes": ["string"],
      "formulas": [
        {
          "expressao": "string",
          "variaveis": [{"nome": "string", "significado": "string"}]
        }
      ],
      "hipoteses": {"explicitas": ["string"], "implicitas": ["string"]},
      "parametros": [{"nome": "string", "valor_definido": true, "valor": "string ou null", "descricao": "string"}],
      "escopo_declarado": {"produtos": ["string"], "carteiras": ["string"], "moedas": ["string"]},
      "tipo": "padronizado_regulatorio ou interno_proprietario"
    }
  ]
}

Regras obrigatórias:
- **Extraia TODAS as fórmulas do texto, não só a fórmula final.** Se uma fórmula usa uma variável que o texto define através de OUTRA fórmula (ex.: "EAD = alpha * (RC + PFE)" e, em outra seção, "PFE = multiplicador * AddOn_total", e "AddOn_total = soma de AddOn_HS..."), inclua CADA UMA dessas fórmulas como um item separado na lista `formulas` — nunca deixe uma variável "pendurada" sem a fórmula que a define, se essa fórmula existe em algum lugar do texto. Documentos técnicos complexos costumam ter 5-15 fórmulas encadeadas; extraia a cadeia inteira.
- `variaveis` é uma LISTA de objetos `{"nome": ..., "significado": ...}`, um por variável da fórmula — nunca um dicionário com chaves literais "nome_variavel"/"significado".
- Para tabelas de parâmetros com múltiplos valores (ex.: um fator diferente por categoria/classe), extraia cada linha da tabela como uma string legível dentro de `valor` (ex.: "Juros: 0,50%; Câmbio: 4,00%; Crédito: 0,46%") — preserve todos os pares categoria→valor, não resuma nem escolha só um.
- Se um parâmetro não tiver valor definido explicitamente no texto, marque "valor_definido": false e "valor": null — isso alimenta o log de decisões de replicabilidade, então não infira valores que não estão escritos.
- Nunca invente fórmulas, números de norma, ou conteúdo que não esteja no texto.
- Se o texto não descrever nenhuma métrica de risco reconhecível, responda {"metrics": []}.

TEXTO METODOLÓGICO:
---
{texto}
---
