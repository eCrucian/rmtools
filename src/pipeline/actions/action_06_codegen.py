"""Action 06 — Geração de código de referência (CLAUDE.md §Action 06).

Regra crítica (§6.1): esta action só pode ler `results["02_extract_model_spec"]`
e `decisions_log` — nunca o texto/arquivo de código-exemplo anexado à
documentação original (que a Action 01 mantém deliberadamente fora de
`methodological_text`). O prompt de geração (`prompts/06_generate_reference_code/
codegen.md`) só recebe nome/fórmulas/parâmetros da métrica extraída — nenhuma
referência a `documents` ou a qualquer conteúdo marcado `is_code_example=True`
existe neste módulo.

Fluxo por métrica: (1) resolve parâmetros ambíguos ANTES de codificar,
logando cada decisão (§Action 06 — "antes de codificar, não depois"); (2)
monta o prompt só com a especificação; (3) pede código ao LLM; (4) roda em
sandbox isolado (`_sandbox.py`) contra a carteira base (§5); (5) se falhar,
reenvia o erro pedindo correção (até `MAX_ATTEMPTS`); (6) se aceito, escreve
`src/metrics/<nome>.py` e registra a versão em `code_versions`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from src.pipeline.contracts import ActionResult, RunContext

from . import _sandbox
from ._common import REPO_ROOT, frozen_portfolio_available, load_prompt_template, sha256_bytes

ACTION_ID = "06_generate_reference_code"
MAX_ATTEMPTS = 5  # métricas multi-componente (ex.: SA-CCR) legitimamente podem levar mais de 3
# tentativas para um modelo pequeno (qwen3:4b) produzir Python sintaticamente válido —
# observado na prática (erros de string não fechada em respostas mais longas/complexas).
METRICS_DIR = REPO_ROOT / "src" / "metrics"

_SYSTEM = (
    "Você é um Quant Developer gerando código Python de referência a partir de uma "
    "especificação textual de uma métrica de risco. Responda apenas com código-fonte Python, "
    "sem markdown, sem explicação."
)

# Heurísticas de default para parâmetros sem valor definido na documentação
# (§Action 06 — decisão de implementação registrada em decisions_log antes de
# codificar). Convenções de mercado comuns, não específicas de nenhuma norma.
_DEFAULT_PARAM_HEURISTICS: tuple[tuple[str, float], ...] = (
    ("confian", 0.99),
    ("janela", 252.0),
    ("window", 252.0),
    ("decaimento", 0.94),
    ("lambda", 0.94),
    ("ewma", 0.94),
    ("horizonte", 1.0),
    ("holding", 1.0),
)


def _sanitize_module_name(nome: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", nome.lower()).strip("_")
    slug = slug or "metrica_sem_nome"
    if slug[0].isdigit():
        slug = f"m_{slug}"
    return slug


def _default_for_param(nome: str) -> tuple[float | None, str]:
    lowered = nome.lower()
    for keyword, default in _DEFAULT_PARAM_HEURISTICS:
        if keyword in lowered:
            return default, f"convenção de mercado para parâmetros cujo nome contém '{keyword}'"
    return None, "sem convenção de mercado aplicável para este nome de parâmetro"


_SINGLE_NUMBER_RE = re.compile(r"^-?\d{1,3}(\.\d{3})*(,\d+)?$|^-?\d+(,\d+)?$")


def _normalize_param_value(valor):
    """Converte um valor numérico em formato brasileiro (vírgula decimal,
    '%' de percentual) para `float` — encontrado na prática: um modelo
    pequeno recebeu `params['SF_fx'] = '4,00%'` sem converter e tentou
    `SF_fx * outro_float`, gerando `TypeError`. Só converte quando o texto
    INTEIRO é inequivocamente um único número — uma string com vários
    valores (ex.: tabela 'Juros: 0,50%; Câmbio: 4,00%') não bate no regex e
    fica como string, para o código gerado (ou uma decisão logada) tratar."""
    if not isinstance(valor, str):
        return valor
    text = valor.strip()
    is_percent = text.endswith("%")
    if is_percent:
        text = text[:-1].strip()
    if not _SINGLE_NUMBER_RE.fullmatch(text):
        return valor
    try:
        number = float(text.replace(".", "").replace(",", "."))
    except ValueError:  # pragma: no cover - o regex acima já restringe `text` a dígitos/vírgula/ponto
        # numa forma que sempre produz um float válido após a troca de separador; mantido como
        # defesa extra caso o regex seja relaxado no futuro sem revisar esta função junto.
        return valor
    return number / 100.0 if is_percent else number


def _resolve_params(ctx: RunContext, metric_nome: str, parametros: list[dict]) -> dict:
    resolved: dict = {}
    for param in parametros:
        nome = param.get("nome", "?")
        if param.get("valor_definido"):
            resolved[nome] = _normalize_param_value(param.get("valor"))
            continue

        default, justificativa = _default_for_param(nome)
        resolved[nome] = default
        ctx.memory.log_decision(
            run_id=ctx.run_id,
            action_id=ACTION_ID,
            campo_afetado=f"{metric_nome}.parametro.{nome}",
            ambiguidade_encontrada=f"Parâmetro '{nome}' da métrica '{metric_nome}' não tinha valor definido na documentação.",
            decisao_tomada=(
                f"Valor default assumido para a implementação de referência: {default!r}."
                if default is not None
                else "Nenhuma convenção de mercado aplicável; parâmetro passado como None — o código "
                "gerado deve tratá-lo como obrigatório/exposto, não inventar um número."
            ),
            justificativa=justificativa,
            fonte_da_decisao="convenção de mercado" if default is not None else "assunção conservadora",
            criticidade="media" if default is not None else "alta",
        )
    return resolved


def _build_prompt(nome: str, formulas: list, params: dict) -> str:
    template = load_prompt_template(ACTION_ID, "codegen.md")
    return (
        template.replace("{nome}", nome)
        .replace("{formulas}", json.dumps(formulas, ensure_ascii=False))
        .replace("{params}", json.dumps(params, ensure_ascii=False))
    )


def _strip_markdown_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines)
    return stripped


def _generate_one_metric(ctx: RunContext, metric: dict, portfolio: dict, risk_factors: dict) -> dict:
    nome = metric.get("nome", "metrica_sem_nome")
    module_name = _sanitize_module_name(nome)
    params = _resolve_params(ctx, nome, metric.get("parametros", []))

    prompt = _build_prompt(nome, metric.get("formulas", []), params)
    last_reason = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        response = ctx.llm_client.complete(system=_SYSTEM, user=prompt, response_schema=None, temperature=0.0)
        ctx.memory.log_llm_call(ctx.run_id, ACTION_ID, response)
        source = _strip_markdown_fences(response.text)

        sandbox_result = _sandbox.run_in_sandbox(
            source, module_name=module_name, portfolio=portfolio, risk_factors=risk_factors, params=params
        )

        if sandbox_result.accepted:
            code_hash = sha256_bytes(source.encode("utf-8"))
            module_path = METRICS_DIR / f"{module_name}.py"
            METRICS_DIR.mkdir(parents=True, exist_ok=True)
            module_path.write_text(source, encoding="utf-8")
            ctx.memory.record_code_version(
                run_id=ctx.run_id, action_id=ACTION_ID, metric=nome,
                file_path=str(module_path), code_hash=code_hash,
            )
            return {
                "status": "success",
                "nome": nome,
                "module_name": module_name,
                "path": str(module_path),
                "attempts": attempt,
                "sample_result": sandbox_result.result,
                "params": params,
            }

        last_reason = sandbox_result.rejection_reason or sandbox_result.stderr or "motivo desconhecido"
        ctx.memory.log_decision(
            run_id=ctx.run_id,
            action_id=ACTION_ID,
            campo_afetado=f"{nome}.codigo_gerado.tentativa_{attempt}",
            ambiguidade_encontrada="N/A — tentativa de geração de código rejeitada pelo sandbox.",
            decisao_tomada=f"Tentativa {attempt}/{MAX_ATTEMPTS} rejeitada: {last_reason[:300]}",
            justificativa="bug_do_agente (código gerado pelo LLM não passou na checagem estática ou na "
            "execução em sandbox) — não é lacuna da documentação, é falha de geração.",
            fonte_da_decisao="assunção conservadora",
            criticidade="baixa" if attempt < MAX_ATTEMPTS else "media",
        )

        prompt = (
            f"{prompt}\n\n---\nA tentativa anterior falhou com o seguinte erro/motivo:\n{last_reason}\n"
            "Corrija o código e responda de novo APENAS com o código-fonte Python completo da função "
            "`compute`, sem markdown."
        )

    return {"status": "failed", "nome": nome, "module_name": module_name, "reason": last_reason}


def run(ctx: RunContext) -> ActionResult:
    extraction = ctx.results["02_extract_model_spec"]
    metrics = extraction.output.get("metrics", [])

    if not metrics:
        return ActionResult(
            status="needs_human_review",
            output={"modules": []},
            notes=["Nenhuma métrica extraída (Action 02) — nada para gerar código."],
        )

    if not frozen_portfolio_available():
        return ActionResult(
            status="needs_human_review",
            output={"modules": [], "metrics_pendentes": [m.get("nome") for m in metrics]},
            notes=[
                "Geração de código de referência bloqueada: a carteira hipotética e os dados "
                "congelados (§5 — data/risk_factors/*.csv, data/pricing_models/) ainda não "
                "existem neste repositório. O DoD da Action 06 exige rodar o código sem erro "
                "contra a carteira base antes de aceitar a versão final; gerar código sem "
                "poder testá-lo produziria uma implementação não verificada.",
            ],
        )

    from src.portfolio import data_access
    from src.portfolio.base_portfolio import POSITIONS
    from src.portfolio.portfolio_history import build_portfolio_input, compute_portfolio_value_series

    # Computa a série de valor uma única vez e deriva os retornos dela
    # (não chama compute_portfolio_returns(), que recalcularia a série do zero).
    value_series = compute_portfolio_value_series()
    returns_series = value_series.pct_change().dropna()

    last_date_market = {name: float(s.iloc[-1]) for name, s in data_access.load_all_risk_factors().items()}
    portfolio_input = build_portfolio_input(POSITIONS, last_date_market)
    risk_factors_input = {"returns": [float(v) for v in returns_series.to_list()]}

    modules = []
    pending = []
    for metric in metrics:
        outcome = _generate_one_metric(ctx, metric, portfolio_input, risk_factors_input)
        if outcome["status"] == "success":
            modules.append(outcome)
        else:
            pending.append(outcome)

    status = "needs_human_review" if pending else "success"
    notes = [f"{len(modules)}/{len(metrics)} métrica(s) geradas e aceitas em sandbox."]
    if pending:
        notes.append(
            "Pendentes: " + "; ".join(f"{p['nome']} ({p.get('reason', '')[:120]})" for p in pending)
        )

    return ActionResult(
        status=status,
        output={"modules": modules, "metrics_pendentes": [p["nome"] for p in pending]},
        artifacts=[Path(m["path"]) for m in modules],
        notes=notes,
    )
