"""Testes dos backends concretos (Azure/Ollama) com a chamada de rede mockada
via monkeypatch de urllib.request.urlopen — nenhum destes testes toca a rede."""

from __future__ import annotations

import json
import urllib.error

import pytest

from src.llm.azure_client import AzureOpenAIClient
from src.llm.ollama_client import OllamaClient


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_ollama_call_raw_parses_response(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout=120: _FakeResponse({"response": '{"metrics": []}', "prompt_eval_count": 10, "eval_count": 5}),
    )
    client = OllamaClient(host="http://localhost:11434", model="qwen3:4b-q4_k_m")
    text, tokens_in, tokens_out = client._call_raw("sys", "user", temperature=0.0)

    assert text == '{"metrics": []}'
    assert tokens_in == 10
    assert tokens_out == 5


def test_ollama_client_default_timeout():
    from src.llm.ollama_client import DEFAULT_TIMEOUT_SECONDS

    client = OllamaClient()
    assert client.timeout == DEFAULT_TIMEOUT_SECONDS


def test_ollama_client_explicit_timeout_overrides_default():
    client = OllamaClient(timeout=42)
    assert client.timeout == 42


def test_ollama_client_timeout_from_env_var(monkeypatch):
    monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", "17")
    client = OllamaClient()
    assert client.timeout == 17


def test_ollama_call_raw_passes_configured_timeout(monkeypatch):
    seen_timeouts = []

    def _fake_urlopen(req, timeout=None):
        seen_timeouts.append(timeout)
        return _FakeResponse({"response": "ok", "prompt_eval_count": 1, "eval_count": 1})

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    client = OllamaClient(timeout=7)
    client._call_raw("sys", "user", temperature=0.0)

    assert seen_timeouts == [7]


def test_ollama_client_default_num_predict():
    from src.llm.ollama_client import DEFAULT_NUM_PREDICT

    client = OllamaClient()
    assert client.num_predict == DEFAULT_NUM_PREDICT


def test_ollama_client_explicit_num_predict_overrides_default():
    client = OllamaClient(num_predict=999)
    assert client.num_predict == 999


def test_ollama_client_num_predict_from_env_var(monkeypatch):
    monkeypatch.setenv("OLLAMA_NUM_PREDICT", "123")
    client = OllamaClient()
    assert client.num_predict == 123


def test_ollama_call_raw_sends_num_predict_in_request_options(monkeypatch):
    seen_payloads = []

    def _fake_urlopen(req, timeout=None):
        seen_payloads.append(json.loads(req.data.decode("utf-8")))
        return _FakeResponse({"response": "ok", "prompt_eval_count": 1, "eval_count": 1})

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    client = OllamaClient(num_predict=2048)
    client._call_raw("sys", "user", temperature=0.0)

    assert seen_payloads[0]["options"]["num_predict"] == 2048


def test_ollama_client_default_num_ctx():
    from src.llm.ollama_client import DEFAULT_NUM_CTX

    client = OllamaClient()
    assert client.num_ctx == DEFAULT_NUM_CTX


def test_ollama_client_explicit_num_ctx_overrides_default():
    client = OllamaClient(num_ctx=16384)
    assert client.num_ctx == 16384


def test_ollama_client_num_ctx_from_env_var(monkeypatch):
    monkeypatch.setenv("OLLAMA_NUM_CTX", "1024")
    client = OllamaClient()
    assert client.num_ctx == 1024


def test_ollama_call_raw_sends_num_ctx_in_request_options(monkeypatch):
    seen_payloads = []

    def _fake_urlopen(req, timeout=None):
        seen_payloads.append(json.loads(req.data.decode("utf-8")))
        return _FakeResponse({"response": "ok", "prompt_eval_count": 1, "eval_count": 1})

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    client = OllamaClient(num_ctx=8192)
    client._call_raw("sys", "user", temperature=0.0)

    assert seen_payloads[0]["options"]["num_ctx"] == 8192


def test_ollama_client_disable_thinking_defaults_to_true():
    assert OllamaClient().disable_thinking is True


def test_ollama_call_raw_sends_think_false_by_default(monkeypatch):
    seen_payloads = []

    def _fake_urlopen(req, timeout=None):
        seen_payloads.append(json.loads(req.data.decode("utf-8")))
        return _FakeResponse({"response": "ok", "prompt_eval_count": 1, "eval_count": 1})

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    client = OllamaClient()
    client._call_raw("sys", "minha pergunta", temperature=0.0)

    # "think" é campo top-level da API do Ollama (não dentro de "options") —
    # confirmado via curl direto contra o servidor real que esse é o que
    # efetivamente desativa o raciocínio estendido do qwen3.
    assert seen_payloads[0]["think"] is False
    assert seen_payloads[0]["prompt"] == "minha pergunta"  # prompt não é mais modificado


def test_ollama_call_raw_sends_think_true_when_thinking_enabled(monkeypatch):
    seen_payloads = []

    def _fake_urlopen(req, timeout=None):
        seen_payloads.append(json.loads(req.data.decode("utf-8")))
        return _FakeResponse({"response": "ok", "prompt_eval_count": 1, "eval_count": 1})

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    client = OllamaClient(disable_thinking=False)
    client._call_raw("sys", "minha pergunta", temperature=0.0)

    assert seen_payloads[0]["think"] is True


def test_ollama_call_raw_strips_residual_think_block(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout=None: _FakeResponse(
            {"response": "<think>deixa eu pensar...</think>\ndef compute(): pass", "prompt_eval_count": 1, "eval_count": 1}
        ),
    )
    client = OllamaClient()
    text, _, _ = client._call_raw("sys", "user", temperature=0.0)

    assert text == "def compute(): pass"
    assert "<think>" not in text


def test_ollama_call_raw_handles_response_with_no_think_block(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout=None: _FakeResponse({"response": "def compute(): pass", "prompt_eval_count": 1, "eval_count": 1}),
    )
    client = OllamaClient()
    text, _, _ = client._call_raw("sys", "user", temperature=0.0)

    assert text == "def compute(): pass"


def test_ollama_call_raw_network_error_raises_runtime_error(monkeypatch):
    def _raise(req, timeout=120):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", _raise)
    client = OllamaClient(host="http://localhost:11434", model="qwen3:4b-q4_k_m")

    with pytest.raises(RuntimeError, match="Ollama"):
        client._call_raw("sys", "user", temperature=0.0)


def test_ollama_client_complete_end_to_end(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout=120: _FakeResponse({"response": '{"metrics": []}', "prompt_eval_count": 1, "eval_count": 1}),
    )
    client = OllamaClient()
    resp = client.complete("sys", "user", response_schema={"type": "object", "required": ["metrics"]})

    assert resp.backend == "ollama"
    assert resp.parsed == {"metrics": []}


def test_azure_client_requires_env_vars():
    with pytest.raises(RuntimeError):
        AzureOpenAIClient(endpoint=None, api_key=None, deployment=None)


def test_azure_call_raw_parses_response(monkeypatch):
    payload = {
        "choices": [{"message": {"content": '{"itens": []}'}}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 8},
    }
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=120: _FakeResponse(payload))

    client = AzureOpenAIClient(
        endpoint="https://example.openai.azure.com",
        api_key="fake-key",
        deployment="fake-deployment",
        api_version="2024-10-21",
    )
    text, tokens_in, tokens_out = client._call_raw("sys", "user", temperature=0.0)

    assert text == '{"itens": []}'
    assert tokens_in == 20
    assert tokens_out == 8


def test_azure_call_raw_network_error_raises_runtime_error(monkeypatch):
    def _raise(req, timeout=120):
        raise urllib.error.URLError("timeout")

    monkeypatch.setattr("urllib.request.urlopen", _raise)
    client = AzureOpenAIClient(endpoint="https://example.openai.azure.com", api_key="k", deployment="d")

    with pytest.raises(RuntimeError, match="Azure"):
        client._call_raw("sys", "user", temperature=0.0)
