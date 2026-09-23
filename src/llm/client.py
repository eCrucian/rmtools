"""Contrato mínimo do LLM client (CLAUDE.md §2.1).

Dois backends concretos implementam `LLMClient`: AzureOpenAIClient (produção) e
OllamaClient (dev/teste local, `qwen3:4b-q4_k_m`). Ambos herdam de
`_RepairingLLMClient`, que centraliza o parsing defensivo + repair prompt exigido
pela regra de §2.1 (modelo pequeno, raciocínio menos confiável): JSON estrito com
schema explícito -> valida -> se falhar, reenvia o erro pedindo correção -> se
falhar de novo, `parsed=None` (quem chama decide marcar `needs_human_review`).
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import NamedTuple, Protocol


class LLMResponse(NamedTuple):
    text: str
    parsed: dict | None
    backend: str
    model: str
    prompt_hash: str
    tokens_in: int
    tokens_out: int
    latency_ms: float


class LLMClient(Protocol):
    def complete(
        self,
        system: str,
        user: str,
        *,
        response_schema: dict | None = None,
        temperature: float = 0.0,
        max_retries: int = 2,
    ) -> LLMResponse: ...


def _prompt_hash(system: str, user: str) -> str:
    return "sha256:" + hashlib.sha256((system + "\n" + user).encode("utf-8")).hexdigest()


def _validate_against_schema(parsed: object, schema: dict) -> list[str]:
    """Validação estrutural leve (não é um validador JSON Schema completo — só
    stdlib está assumido como disponível, §2.2). Cobre o suficiente para os
    prompts deste pipeline: required de top-level e tipos básicos de properties.
    """
    errors: list[str] = []
    expected_type = schema.get("type")
    if expected_type == "object" and not isinstance(parsed, dict):
        return [f"esperado objeto JSON, recebido {type(parsed).__name__}"]
    if expected_type == "array" and not isinstance(parsed, list):
        return [f"esperado array JSON, recebido {type(parsed).__name__}"]
    if not isinstance(parsed, dict):
        return errors

    for key in schema.get("required", []):
        if key not in parsed:
            errors.append(f"campo obrigatório ausente: '{key}'")

    type_map = {
        "string": str,
        "number": (int, float),
        "integer": int,
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    for key, subschema in schema.get("properties", {}).items():
        if key not in parsed:
            continue
        expected = subschema.get("type")
        py_type = type_map.get(expected)
        if py_type is not None and not isinstance(parsed[key], py_type):
            errors.append(f"campo '{key}' deveria ser '{expected}', recebido {type(parsed[key]).__name__}")
    return errors


class _RepairingLLMClient:
    """Implementa o loop de repair prompt sobre um `_call_raw` fornecido pela
    subclasse concreta (Azure ou Ollama)."""

    backend: str
    model: str

    def _call_raw(self, system: str, user: str, *, temperature: float) -> tuple[str, int, int]:
        """Retorna (texto_bruto, tokens_in, tokens_out). Implementado por subclasse."""
        raise NotImplementedError

    def complete(
        self,
        system: str,
        user: str,
        *,
        response_schema: dict | None = None,
        temperature: float = 0.0,
        max_retries: int = 2,
    ) -> LLMResponse:
        start = time.monotonic()
        prompt_hash = _prompt_hash(system, user)

        current_user = user
        text = ""
        tokens_in = 0
        tokens_out = 0
        parsed: dict | None = None

        attempts = max(1, max_retries + 1)
        for attempt in range(attempts):
            text, t_in, t_out = self._call_raw(system, current_user, temperature=temperature)
            tokens_in += t_in
            tokens_out += t_out

            if response_schema is None:
                parsed = None
                break

            try:
                candidate = json.loads(text)
            except (json.JSONDecodeError, ValueError) as exc:
                errors = [f"JSON inválido: {exc}"]
                candidate = None
            else:
                errors = _validate_against_schema(candidate, response_schema)

            if not errors:
                parsed = candidate
                break

            parsed = None
            if attempt < attempts - 1:
                current_user = (
                    f"{user}\n\n---\nA resposta anterior falhou na validação de schema. "
                    f"Erros encontrados: {'; '.join(errors)}. "
                    f"Responda novamente APENAS com JSON estrito que satisfaça o schema:\n"
                    f"{json.dumps(response_schema, ensure_ascii=False)}"
                )

        latency_ms = (time.monotonic() - start) * 1000
        return LLMResponse(
            text=text,
            parsed=parsed,
            backend=self.backend,
            model=self.model,
            prompt_hash=prompt_hash,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
        )


def get_llm_client(backend: str | None = None) -> LLMClient:
    """Factory (CLAUDE.md §2.1): seleção via LLM_BACKEND=azure|ollama."""
    backend = (backend or os.environ.get("LLM_BACKEND", "ollama")).lower()
    if backend == "azure":
        from .azure_client import AzureOpenAIClient

        return AzureOpenAIClient()
    if backend == "ollama":
        from .ollama_client import OllamaClient

        return OllamaClient()
    raise ValueError(f"LLM_BACKEND desconhecido: '{backend}' (esperado 'azure' ou 'ollama')")
