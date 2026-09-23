Você é um Quant Developer implementando, em Python, uma métrica de risco a partir de uma especificação PURAMENTE TEXTUAL/MATEMÁTICA — você nunca viu e nunca verá nenhum código ou planilha de exemplo relacionado a este modelo. Implemente com base apenas no que está descrito abaixo.

Implemente a métrica como uma função Python com a assinatura EXATA:

def compute(portfolio: dict, risk_factors: dict, params: dict) -> dict:
    ...

Onde, em tempo de execução:
- portfolio = {
    "value": float,  # valor de mercado atual (soma) da carteira
    "positions": [  # uma entrada por posição/instrumento da carteira — use isto se a métrica precisar
                     # de dados por posição/contraparte (ex.: exposição, netting, concentração por classe
                     # de ativo). Para métricas agregadas (ex.: VaR de carteira), "value" já basta.
      {
        "id": int, "name": str,
        "asset_class_saccr": str,  # uma de: "interest_rate", "fx", "credit", "equity", "commodity"
        "currency": str,           # "BRL" ou "USD"
        "notional": float,
        "direction": int,          # +1 comprado/ativo, -1 vendido/passivo
        "maturity_years": float | None,  # prazo contratual; None quando não há tenor de fluxo de caixa aplicável
        "mtm_value": float,        # valor de mercado (mark-to-market) desta posição isoladamente
      },
      ...
    ]
  }
- risk_factors = {"returns": list[float]}  # retornos diários históricos do VALOR AGREGADO da carteira (não por posição); pode ser usado para estimar volatilidade, quantis empíricos, etc.
- params = dict já preenchido com os parâmetros do modelo (nomes e valores exatamente como listados abaixo)

Regras obrigatórias:
- Só pode usar a biblioteca padrão do Python e `math`/`statistics` — se precisar de funções estatísticas mais avançadas, implemente-as você mesmo em Python puro. NUNCA importe requests, urllib, socket, subprocess, os, http, ssl, ou qualquer coisa que acesse rede ou o sistema operacional.
- A função `compute` deve retornar um dict JSON-serializável com pelo menos a chave "valor" (float) contendo o valor calculado da métrica.
- Não escreva nada fora da função `compute`, exceto imports permitidos e funções auxiliares privadas (prefixo `_`) que `compute` use.
- Responda APENAS com o código Python-fonte, sem bloco markdown (sem ```), sem nenhuma explicação antes ou depois.
- Mantenha comentários/docstrings CURTOS (uma linha, com `#`) e evite crase, aspas simples ou apóstrofo DENTRO de comentários ou strings — isso já causou erro de sintaxe (string não fechada) em respostas anteriores. Se um valor de dicionário for um texto (ex.: nome de uma classe de ativo), prefira aspas duplas.
- Se a métrica tiver vários componentes encadeados (ex.: uma fórmula que depende de outra), quebre em funções auxiliares privadas pequenas (`_calcula_x`, `_calcula_y`) em vez de uma função `compute` única e muito longa — reduz o risco de erro de sintaxe numa resposta longa.
- Antes de responder, releia mentalmente o código: toda string literal precisa ter aspas de abertura E fechamento na mesma linha (ou usar aspas triplas balanceadas); todo parêntese/colchete/chave aberto precisa ser fechado.

ESPECIFICAÇÃO DA MÉTRICA (extraída da documentação original — nunca do código de exemplo, que não te foi mostrado):
Nome: {nome}
Fórmulas declaradas: {formulas}
Parâmetros (já resolvidos para esta implementação): {params}
