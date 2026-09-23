"""Backend Ollama (`qwen3:4b-q4_k_m`) — dev/teste local a custo zero (CLAUDE.md §2.1)."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

from .client import _RepairingLLMClient

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


DEFAULT_TIMEOUT_SECONDS = 300  # inferência local em CPU para prompts complexos (ex.: codegen §Action 06) pode
# passar de 2 minutos com um modelo pequeno (qwen3:4b) — 120s se mostrou curto demais na prática
# (timeout real observado gerando código para uma métrica multi-componente, doc_boa/SA-CCR).

DEFAULT_NUM_PREDICT = 4096  # o default do Ollama para este modelo se mostrou curto demais na prática:
# uma resposta de codegen mais longa (doc_boa/SA-CCR) foi cortada no meio de uma string literal,
# gerando um SyntaxError espúrio — nada a ver com a qualidade do código em si.

DEFAULT_NUM_CTX = 8192  # o RUNTIME do Ollama usa um default pequeno (historicamente 2048) para a
# janela de contexto, independente do que o modelo em si suporta (qwen3:4b-q4_k_m suporta 40960) —
# sem setar isso explicitamente, prompt + num_predict grandes competem pelo mesmo espaço pequeno e
# a resposta pode sair vazia (observado na prática: nenhum erro, só um response="" silencioso).

# qwen3 é um modelo de "raciocínio" (pensa em um bloco <think>...</think> antes de responder) —
# encontrado na prática: para um prompt de codegen complexo (§Action 06, SA-CCR), o modelo gastou
# os 4096 tokens de num_predict inteiros "pensando" e nunca chegou a emitir a resposta final
# (response="" mesmo com tokens_out=4096). A diretiva de prompt "/no_think" documentada do Qwen3
# NÃO funcionou de forma confiável via /api/generate (mesmo sintoma se repetiu) — o parâmetro
# NATIVO da API do Ollama (`"think": false`, top-level, não dentro de "options") funcionou de
# forma limpa e confirmada (testado via curl: resposta direta, poucos tokens). Além de resolver o
# estouro de budget, é mais rápido (menos tokens gerados por chamada), o que importa rodando
# localmente na GPU/CPU do usuário.


class OllamaClient(_RepairingLLMClient):
    backend = "ollama"

    def __init__(
        self,
        host: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
        num_predict: int | None = None,
        num_ctx: int | None = None,
        disable_thinking: bool = True,
    ):
        self.host = host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self.model = model or os.environ.get("OLLAMA_MODEL", "qwen3:4b-q4_k_m")
        self.timeout = timeout or int(os.environ.get("OLLAMA_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
        self.num_predict = num_predict or int(os.environ.get("OLLAMA_NUM_PREDICT", DEFAULT_NUM_PREDICT))
        self.num_ctx = num_ctx or int(os.environ.get("OLLAMA_NUM_CTX", DEFAULT_NUM_CTX))
        self.disable_thinking = disable_thinking

    def _call_raw(self, system: str, user: str, *, temperature: float) -> tuple[str, int, int]:
        payload = json.dumps(
            {
                "model": self.model,
                "system": system,
                "prompt": user,
                "stream": False,
                "think": not self.disable_thinking,
                "options": {"temperature": temperature, "num_predict": self.num_predict, "num_ctx": self.num_ctx},
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self.host.rstrip('/')}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(
                f"Falha ao chamar Ollama em {self.host} (modelo {self.model}, timeout={self.timeout}s): {exc}. "
                "Verifique se `ollama serve` está rodando localmente."
            ) from exc

        text = body.get("response", "")
        # Defesa extra: mesmo com /no_think, remove qualquer bloco <think>...</think>
        # residual antes de devolver — nunca deixar rastro de raciocínio vazar para o
        # parsing de JSON/código a jusante.
        text = _THINK_BLOCK_RE.sub("", text).strip()
        tokens_in = body.get("prompt_eval_count", 0) or 0
        tokens_out = body.get("eval_count", 0) or 0
        return text, tokens_in, tokens_out
