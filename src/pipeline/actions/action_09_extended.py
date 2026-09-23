"""Action 09 — Esteira de testes extensível (CLAUDE.md §Action 09).

Registry plugável: lê config/extended_tests.yaml, roda o que estiver
`enabled: true` (importando `src.tests_extended.<id>.run`), e lista o que
estiver `enabled: false` como "planejado, não implementado". Os dois testes
habilitados por padrão (`concentration_test`, `liquidity_horizon_scaling`)
reaproveitam os resultados já calculados pela Action 07 — se ela não rodou
(sem módulos de métrica ainda), cada um retorna `skipped` por conta própria.
"""

from __future__ import annotations

import importlib

from src.pipeline.contracts import ActionResult, RunContext

from ._common import CONFIG_DIR
from ..config import load_yaml

ACTION_ID = "09_extended_test_suite"


def run(ctx: RunContext) -> ActionResult:
    registry_path = CONFIG_DIR / "extended_tests.yaml"
    registry = load_yaml(registry_path) or {}
    entries = registry.get("extended_tests", [])

    executed = []
    pending = []
    notes = []

    for entry in entries:
        test_id = entry.get("id")
        if not entry.get("enabled", False):
            pending.append({"id": test_id, "description": entry.get("description", "")})
            continue
        try:
            module = importlib.import_module(f"src.tests_extended.{test_id}")
        except ImportError as exc:
            notes.append(f"'{test_id}' está enabled: true mas o módulo src.tests_extended.{test_id} falhou ao importar: {exc}")
            pending.append({"id": test_id, "description": entry.get("description", ""), "erro": str(exc)})
            continue
        result: ActionResult = module.run(ctx)
        executed.append({"id": test_id, "status": result.status, "output": result.output})

    output = {"executados": executed, "pendentes": pending}
    ctx.memory.write_output("extended_tests", ctx.run_id, ACTION_ID, output)

    notes.append(f"{len(executed)} teste(s) executado(s), {len(pending)} pendente(s)/planejado(s).")
    return ActionResult(status="success", output=output, notes=notes)
