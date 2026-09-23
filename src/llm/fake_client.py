"""Double de LLMClient para testes — sem rede, respostas programadas.

Não é um dos dois backends de produção do CLAUDE.md §2.1; existe só para permitir
testar a lógica das actions isoladamente (§3.2 exige testes por action/métrica,
que não podem depender de um Ollama local rodando).
"""

from __future__ import annotations

import json

from .client import LLMResponse, _prompt_hash, _validate_against_schema


class FakeLLMClient:
    backend = "fake"
    model = "fake-model"

    def __init__(self, responses: list[dict | str] | None = None):
        """`responses`: fila de respostas a devolver em chamadas sucessivas
        (dict -> serializado como JSON; str -> devolvida como texto cru)."""
        self._queue = list(responses or [])
        self.calls: list[tuple[str, str]] = []

    def complete(
        self,
        system: str,
        user: str,
        *,
        response_schema: dict | None = None,
        temperature: float = 0.0,
        max_retries: int = 2,
    ) -> LLMResponse:
        self.calls.append((system, user))
        if self._queue:
            item = self._queue.pop(0)
        else:
            item = {} if response_schema is not None else ""
        text = json.dumps(item, ensure_ascii=False) if isinstance(item, dict) else str(item)

        parsed = None
        if response_schema is not None:
            try:
                candidate = json.loads(text)
            except (json.JSONDecodeError, ValueError):
                candidate = None
            if candidate is not None and not _validate_against_schema(candidate, response_schema):
                parsed = candidate

        return LLMResponse(
            text=text,
            parsed=parsed,
            backend=self.backend,
            model=self.model,
            prompt_hash=_prompt_hash(system, user),
            tokens_in=len(user.split()),
            tokens_out=len(text.split()),
            latency_ms=0.0,
        )
