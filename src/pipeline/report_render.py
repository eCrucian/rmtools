"""Renderização do relatório final (CLAUDE.md §9.2).

Regra de conteúdo: nenhum número é digitado à mão — toda tabela/valor citado
vem de uma leitura de `memory/state.db` (via `MemoryStore`). Esta função só
formata o que já está persistido; não inventa nem calcula nada por conta própria.
"""

from __future__ import annotations

from src.memory.db import MemoryStore

try:
    import pandas as pd

    _HAS_PANDAS_MARKDOWN = True
except ImportError:  # pragma: no cover - pandas está nas deps base do projeto
    _HAS_PANDAS_MARKDOWN = False


def _markdown_table(headers: list[str], rows: list[list]) -> str:
    if not rows:
        return "_(nenhum registro)_\n"
    try:
        if _HAS_PANDAS_MARKDOWN:  # pragma: no cover - só o ramo de sucesso; exige `tabulate` instalado
            return pd.DataFrame(rows, columns=headers).to_markdown(index=False) + "\n"
    except ImportError:
        pass  # tabulate ausente — cai no fallback manual abaixo

    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines) + "\n"


def render_markdown(memory: MemoryStore, run_id: str, asset_refs: dict[str, str] | None = None) -> str:
    asset_refs = asset_refs or {}
    run = memory.get_run(run_id) or {}
    decisions = memory.get_decisions(run_id)
    quality = memory.read_outputs("quality_scores", run_id)
    methodology = memory.read_outputs("methodology_assessment", run_id)
    regulatory = memory.read_outputs("regulatory_adherence", run_id)
    stability = memory.read_outputs("stability_results", run_id)
    backtest = memory.read_outputs("backtest_results", run_id)
    extended = memory.read_outputs("extended_tests", run_id)
    action_runs = memory.get_all_action_runs(run_id)

    sections: list[str] = []

    # 1. Sumário executivo
    #
    # O status geral é calculado a partir de `action_runs` (01..09), não lido de
    # `runs.status`: esta própria Action 10 ainda está em execução no momento em
    # que o relatório é montado, então `runs.status` ainda registraria "running"
    # mesmo num relatório final — calcular a partir do que já rodou é o dado
    # correto disponível neste ponto (a run só é marcada finished_at depois que
    # a Action 10 retorna).
    action_statuses = [a["status"] for a in action_runs]
    if any(s == "failed" for s in action_statuses):
        status_geral = "com falha(s) em pelo menos uma action (ver seção 10)"
    elif any(s == "needs_human_review" for s in action_statuses):
        status_geral = "concluído com pendências (needs_human_review — ver seção 10)"
    else:
        status_geral = "concluído sem falhas"

    latest_quality = quality[-1]["data"] if quality else None
    nota_agregada = latest_quality.get("nota_agregada") if latest_quality else "N/D"
    sections.append(
        "## 1. Sumário executivo\n\n"
        f"Run `{run_id}` — status geral: **{status_geral}**. "
        f"Nota de qualidade documental agregada: **{nota_agregada}**. "
        f"{len(backtest)} resultado(s) de backtest, {len(stability)} resultado(s) de estabilidade "
        f"registrados nesta run. Ver seções seguintes para detalhe por métrica.\n"
    )

    # 2. Escopo e metodologia da validação
    sections.append(
        "## 2. Escopo e metodologia da validação\n\n"
        f"- **run_id**: `{run_id}`\n"
        f"- **Documento de origem**: {run.get('doc_source') or 'N/D'}\n"
        f"- **Backend de LLM**: {run.get('backend_llm', 'N/D')}\n"
        f"- **Iniciada em**: {run.get('created_at', 'N/D')}\n"
        f"- **Finalizada em**: {run.get('finished_at') or 'em andamento'}\n"
    )

    # 3. Qualidade da documentação
    if latest_quality:
        rows = [[it.get("item"), it.get("nota"), it.get("evidencia")] for it in latest_quality.get("itens", [])]
        table = _markdown_table(["Item", "Nota (0-4)", "Evidência"], rows)
    else:
        table = "_(Action 03 não produziu score nesta run — ver notas de status por action, seção 8.)_\n"
    sections.append("## 3. Avaliação da qualidade da documentação\n\n" + table)

    # 4. Qualidade metodológica
    if methodology:
        m = methodology[-1]["data"]
        hip_rows = [
            [h.get("hipotese"), h.get("testavel_quantitativamente"), h.get("justificativa_testabilidade")]
            for h in m.get("hipoteses_avaliadas", [])
        ]
        hip_table = _markdown_table(["Hipótese", "Testável?", "Justificativa"], hip_rows)
        ref_rows = [[r.get("referencia"), r.get("referencia_nao_verificada")] for r in m.get("referencias_citadas", [])]
        ref_table = _markdown_table(["Referência", "Não verificada?"], ref_rows)
        limitacoes = "\n".join(f"- {l}" for l in m.get("limitacoes_discutidas", [])) or "_(nenhuma reportada)_"
        methodology_block = (
            f"### Hipóteses avaliadas\n\n{hip_table}\n### Limitações discutidas\n\n{limitacoes}\n\n"
            f"### Referências citadas\n\n{ref_table}"
        )
    else:
        methodology_block = "_(Action 04 não produziu avaliação nesta run.)_\n"
    sections.append("## 4. Avaliação da qualidade metodológica\n\n" + methodology_block)

    # 5. Aderência normativa
    if regulatory:
        r = regulatory[-1]["data"]
        reg_rows = [
            [c.get("clausula"), c.get("requisito"), c.get("tratamento_na_doc"), c.get("aderente"), c.get("observacao")]
            for c in r.get("clausulas", [])
        ]
        reg_table = _markdown_table(["Cláusula", "Requisito", "Tratamento na doc", "Aderente?", "Observação"], reg_rows)
    else:
        reg_table = "_(não aplicável — Action 05 skipped ou não rodou nesta run; ver seção 8.)_\n"
    sections.append("## 5. Aderência normativa\n\n" + reg_table)

    # 6. Testes de estabilidade
    stab_rows = []
    for row in stability:
        d = row["data"]
        stab_rows.append([d.get("metrica"), d.get("fator"), d.get("choque"), d.get("delta_metrica"), d.get("dentro_do_limite")])
    stab_table = _markdown_table(["Métrica", "Fator", "Choque", "Δ Métrica", "Dentro do limite?"], stab_rows)
    stab_chart = (
        f"\n![Elasticidade por choque]({asset_refs['stability_elasticity']})\n"
        if "stability_elasticity" in asset_refs
        else "\n_(gráfico de elasticidade não gerado nesta run — sem resultados de estabilidade com choque isolado.)_\n"
    )
    sections.append("## 6. Testes de estabilidade\n\n" + stab_table + stab_chart)

    # 7. Backtesting
    back_rows = []
    for row in backtest:
        d = row["data"]
        back_rows.append(
            [d.get("metrica"), d.get("holding_period"), d.get("kupiec"), d.get("christoffersen"), d.get("semaforo")]
        )
    back_table = _markdown_table(["Métrica", "Holding period", "Kupiec", "Christoffersen", "Semáforo Basileia"], back_rows)
    back_chart = (
        f"\n![Backtest — perda realizada vs. VaR]({asset_refs['backtest_exceptions']})\n"
        if "backtest_exceptions" in asset_refs
        else "\n_(gráfico de exceções não gerado nesta run — sem resultado de backtest para holding period=1.)_\n"
    )
    sections.append("## 7. Backtesting\n\n" + back_table + back_chart)

    # 8. Replicabilidade
    by_crit = {"alta": [], "media": [], "baixa": []}
    for d in decisions:
        by_crit.setdefault(d["criticidade"], []).append(d)
    decisions_block = []
    for crit in ("alta", "media", "baixa"):
        items = by_crit.get(crit, [])
        decisions_block.append(f"### Criticidade: {crit} ({len(items)})\n")
        if not items:
            decisions_block.append("_(nenhuma)_\n")
            continue
        rows = [
            [d["action_id"], d["campo_afetado"], d["ambiguidade_encontrada"], d["decisao_tomada"], d["fonte_da_decisao"]]
            for d in items
        ]
        decisions_block.append(_markdown_table(["Action", "Campo", "Ambiguidade", "Decisão tomada", "Fonte"], rows))
    extended_block = ""
    if extended:
        ext = extended[-1]["data"]
        extended_block = (
            f"\n### Esteira de testes extensível\n\n"
            f"- Executados: {len(ext.get('executados', []))}\n"
            f"- Pendentes/planejados: {len(ext.get('pendentes', []))} "
            f"({', '.join(p.get('id', '?') for p in ext.get('pendentes', [])) or 'nenhum'})\n"
        )
    sections.append(
        "## 8. Replicabilidade\n\n"
        "### (a) Lacunas da documentação (decisions_log)\n\n" + "\n".join(decisions_block) + extended_block
    )

    # 9. Conclusões e recomendações
    fragilidades = [d for d in decisions if d["criticidade"] == "alta"]
    frag_lines = (
        "\n".join(
            f"- **{d['campo_afetado']}** ({d['action_id']}): {d['ambiguidade_encontrada']} "
            f"— decisão tomada: {d['decisao_tomada']}"
            for d in fragilidades
        )
        or "_(nenhuma fragilidade de criticidade alta registrada nesta run)_"
    )
    sugestoes = [d for d in decisions if d["criticidade"] in ("media", "baixa")]
    sug_lines = (
        "\n".join(f"- {d['campo_afetado']} ({d['action_id']}): {d['ambiguidade_encontrada']}" for d in sugestoes)
        or "_(nenhuma)_"
    )
    sections.append(
        "## 9. Conclusões e recomendações\n\n"
        f"### Fragilidades\n\n{frag_lines}\n\n### Sugestões (nice to have)\n\n{sug_lines}\n"
    )

    # 10. Anexos
    status_rows = [[a["action_id"], a["status"], "; ".join(a["notes"]) or "-"] for a in action_runs]
    status_table = _markdown_table(["Action", "Status", "Notas"], status_rows)
    n_individual_tests = len(stability) + len(backtest)
    if n_individual_tests == 0:
        tests_block = (
            "_(nenhum teste individual de estabilidade/backtest foi registrado nesta run — ver "
            "status das Actions 06/07/08 acima e seção 8 para o motivo.)_\n"
        )
    else:
        tests_block = f"{n_individual_tests} teste(s) individual(is) registrado(s) — ver seções 6 e 7.\n"
    sections.append(
        "## 10. Anexos\n\n"
        "### Status por action nesta run\n\n" + status_table + "\n"
        "### JSONs de teste individuais\n\n" + tests_block
    )

    header = f"# Relatório de Validação Independente — run `{run_id}`\n\n"
    return header + "\n".join(sections)
