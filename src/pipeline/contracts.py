"""Contrato de uma action (CLAUDE.md §3.1) + contexto de execução."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

from src.llm.client import LLMClient
from src.memory.db import MemoryStore

Status = Literal["success", "failed", "needs_human_review", "skipped"]


@dataclass
class ActionResult:
    status: Status
    output: dict[str, Any] = field(default_factory=dict)
    artifacts: list[Path] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class RunContext:
    run_id: str
    memory: MemoryStore
    llm_client: LLMClient
    inputs: dict[str, Any]
    results: dict[str, ActionResult]
    force: bool = False


@dataclass
class ActionSpec:
    id: str
    name: str
    depends_on: list[str]
    input_schema: dict
    output_schema: dict
    prompt_templates: list[str]
    run: Callable[[RunContext], ActionResult]
    idempotent: bool = True
    # True só para 10_replicability_report: seu único trabalho é consolidar o
    # que aconteceu na run (incluindo falhas de fato, §10-a) num relatório —
    # nunca deve ser pulada por uma dependência ter "failed", ou a run inteira
    # fica sem relatório final, violando a regra central do CLAUDE.md de que o
    # pipeline sempre chega a um relatório (§3.3/§8), mesmo sob falha real.
    always_run: bool = False
