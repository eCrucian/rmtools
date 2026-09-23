"""Backend Azure OpenAI (Chat Completions) — produção (CLAUDE.md §2.1)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from .client import _RepairingLLMClient


class AzureOpenAIClient(_RepairingLLMClient):
    backend = "azure"

    def __init__(
        self,
        endpoint: str | None = None,
        api_key: str | None = None,
        deployment: str | None = None,
        api_version: str | None = None,
    ):
        self.endpoint = endpoint or os.environ.get("AZURE_OPENAI_ENDPOINT")
        self.api_key = api_key or os.environ.get("AZURE_OPENAI_API_KEY")
        self.deployment = deployment or os.environ.get("AZURE_OPENAI_DEPLOYMENT")
        self.api_version = api_version or os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21")
        self.model = self.deployment or "azure-openai"

        missing = [
            name
            for name, value in [
                ("AZURE_OPENAI_ENDPOINT", self.endpoint),
                ("AZURE_OPENAI_API_KEY", self.api_key),
                ("AZURE_OPENAI_DEPLOYMENT", self.deployment),
            ]
            if not value
        ]
        if missing:
            raise RuntimeError(
                "AzureOpenAIClient: variáveis de ambiente ausentes: " + ", ".join(missing)
            )

    def _call_raw(self, system: str, user: str, *, temperature: float) -> tuple[str, int, int]:
        url = (
            f"{self.endpoint.rstrip('/')}/openai/deployments/{self.deployment}"
            f"/chat/completions?api-version={self.api_version}"
        )
        payload = json.dumps(
            {
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": temperature,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json", "api-key": self.api_key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"Falha ao chamar Azure OpenAI ({self.deployment}): {exc}") from exc

        text = body["choices"][0]["message"]["content"]
        usage = body.get("usage", {})
        tokens_in = usage.get("prompt_tokens", 0) or 0
        tokens_out = usage.get("completion_tokens", 0) or 0
        return text, tokens_in, tokens_out
