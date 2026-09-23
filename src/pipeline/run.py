"""Executor do pipeline (CLAUDE.md §3.4).

Percorre `ACTIONS` na ordem de inserção do dict (== ordem topológica válida,
`depends_on` existe para validar isso e permitir skip automático de
dependentes). Só uma dependência com status `"failed"` propaga skip automático
para quem depende dela — `needs_human_review` e `skipped` não travam o
pipeline (regra central do CLAUDE.md: nunca parar por causa de má
documentação ou lacuna de dado, só por erro de fato).

Resumabilidade (§2.3): cada action, ao terminar, grava um checkpoint com hash
dos inputs relevantes (specs dependidas + inputs globais da run). Se a run for
reexecutada com o mesmo `run_id` e os inputs não mudaram, a action é pulada
(`status_original` preservado, mas reportada como já resolvida) — a menos que
`force=True`.
"""

from __future__ import annotations

import hashlib
import json

from src.llm.client import LLMClient
from src.memory.db import MemoryStore
from src.pipeline.contracts import ActionResult, RunContext
from src.pipeline.registry import ACTIONS


def _input_hash(action_id: str, inputs: dict, results: dict[str, ActionResult]) -> str:
    spec = ACTIONS[action_id]
    dep_outputs = {dep: results[dep].output for dep in spec.depends_on if dep in results}
    payload = json.dumps({"inputs": inputs, "deps": dep_outputs}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def run_pipeline(
    run_id: str,
    memory: MemoryStore,
    llm_client: LLMClient,
    inputs: dict | None = None,
    force: bool = False,
) -> dict[str, ActionResult]:
    inputs = inputs or {}
    memory.start_run(run_id, doc_source=str(inputs.get("doc_paths")), backend_llm=llm_client.backend)

    results: dict[str, ActionResult] = {}
    failed: set[str] = set()

    for action_id, spec in ACTIONS.items():
        if not spec.always_run and any(dep in failed for dep in spec.depends_on):
            result = ActionResult(
                status="skipped",
                notes=[f"dependência(s) com status 'failed': {[d for d in spec.depends_on if d in failed]}"],
            )
            results[action_id] = result
            memory.save_action_result(run_id, action_id, input_hash="", result=result)
            # Nota: NÃO adiciona action_id a `failed` — o status desta action é
            # "skipped", não "failed". Só falhas de fato devem cascatear; senão
            # uma única falha travaria o pipeline inteiro em vez de só suas
            # dependentes diretas (violaria a regra "nunca travar", §6/§8).
            continue

        input_hash = _input_hash(action_id, inputs, results)
        if not force:
            cached = memory.get_checkpoint(run_id, action_id, input_hash)
            if cached is not None:
                result = ActionResult(status=cached["status"], output=cached["output"], notes=cached["notes"])
                results[action_id] = result
                if result.status == "failed":
                    failed.add(action_id)
                continue

        ctx = RunContext(run_id=run_id, memory=memory, llm_client=llm_client, inputs=inputs, results=results, force=force)
        try:
            result = spec.run(ctx)
        except Exception as exc:  # a action falhou de fato (bug, não lacuna de doc)
            result = ActionResult(status="failed", notes=[f"exceção não tratada: {exc!r}"])

        memory.save_action_result(run_id, action_id, input_hash, result)
        results[action_id] = result
        if result.status == "failed":
            failed.add(action_id)

    overall_status = "failed" if failed else "success"
    memory.finish_run(run_id, overall_status)
    return results
