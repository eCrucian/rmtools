from __future__ import annotations

import pytest

from src.llm import client as client_mod
from src.llm.fake_client import FakeLLMClient


def test_prompt_hash_is_deterministic():
    h1 = client_mod._prompt_hash("sys", "user")
    h2 = client_mod._prompt_hash("sys", "user")
    h3 = client_mod._prompt_hash("sys", "outro")
    assert h1 == h2
    assert h1 != h3
    assert h1.startswith("sha256:")


def test_validate_against_schema_object_type_mismatch():
    errors = client_mod._validate_against_schema(["não é objeto"], {"type": "object"})
    assert errors and "objeto" in errors[0]


def test_validate_against_schema_array_type_mismatch():
    errors = client_mod._validate_against_schema({"a": 1}, {"type": "array"})
    assert errors and "array" in errors[0]


def test_validate_against_schema_missing_required():
    errors = client_mod._validate_against_schema({}, {"type": "object", "required": ["metrics"]})
    assert any("metrics" in e for e in errors)


def test_validate_against_schema_wrong_property_type():
    schema = {"type": "object", "properties": {"nota": {"type": "number"}}}
    errors = client_mod._validate_against_schema({"nota": "não é número"}, schema)
    assert errors


def test_validate_against_schema_non_dict_with_no_type_is_ok():
    assert client_mod._validate_against_schema("string qualquer", {}) == []


def test_validate_against_schema_skips_absent_property():
    schema = {"type": "object", "properties": {"campo_ausente": {"type": "string"}}}
    assert client_mod._validate_against_schema({}, schema) == []


def test_base_repairing_client_call_raw_not_implemented():
    with pytest.raises(NotImplementedError):
        client_mod._RepairingLLMClient()._call_raw("sys", "user", temperature=0.0)


def test_repairing_client_without_schema_skips_validation():
    class NoSchemaFake(client_mod._RepairingLLMClient):
        backend = "fake-noschema"
        model = "fake-model"

        def _call_raw(self, system, user, *, temperature):
            return "texto livre qualquer", 3, 4

    resp = NoSchemaFake().complete("sys", "user")
    assert resp.parsed is None
    assert resp.text == "texto livre qualquer"
    assert resp.tokens_in == 3 and resp.tokens_out == 4


def test_repairing_client_without_schema_returns_none_parsed():
    llm = FakeLLMClient(responses=["texto livre, sem schema"])
    resp = llm.complete("sys", "user")
    assert resp.parsed is None
    assert resp.text == "texto livre, sem schema"


def test_fake_client_empty_queue_without_schema_returns_empty_text():
    llm = FakeLLMClient()
    resp = llm.complete("sys", "user")
    assert resp.text == ""
    assert resp.parsed is None


def test_fake_client_empty_queue_with_schema_returns_empty_object():
    llm = FakeLLMClient()
    resp = llm.complete("sys", "user", response_schema={"type": "object", "required": ["metrics"]})
    assert resp.text == "{}"
    assert resp.parsed is None  # {} não satisfaz o required "metrics"


def test_repairing_client_repair_prompt_eventually_succeeds():
    class RepairingFake(client_mod._RepairingLLMClient):
        backend = "fake-repair"
        model = "fake-model"

        def __init__(self):
            self.attempts = 0

        def _call_raw(self, system, user, *, temperature):
            self.attempts += 1
            if self.attempts < 2:
                return "isso não é JSON", 1, 1
            return '{"metrics": []}', 1, 1

    llm = RepairingFake()
    resp = llm.complete("sys", "user", response_schema={"type": "object", "required": ["metrics"]}, max_retries=2)

    assert resp.parsed == {"metrics": []}
    assert llm.attempts == 2


def test_repairing_client_exhausts_retries_and_gives_up():
    class AlwaysBrokenFake(client_mod._RepairingLLMClient):
        backend = "fake-broken"
        model = "fake-model"

        def _call_raw(self, system, user, *, temperature):
            return "nunca vira JSON válido", 1, 1

    llm = AlwaysBrokenFake()
    resp = llm.complete("sys", "user", response_schema={"type": "object", "required": ["metrics"]}, max_retries=1)

    assert resp.parsed is None


def test_get_llm_client_factory_selects_backend(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    ollama = client_mod.get_llm_client("ollama")
    assert ollama.backend == "ollama"


def test_get_llm_client_factory_unknown_backend_raises():
    with pytest.raises(ValueError):
        client_mod.get_llm_client("nao-existe")


def test_get_llm_client_factory_azure_missing_env_raises(monkeypatch):
    for var in ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_DEPLOYMENT"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(RuntimeError):
        client_mod.get_llm_client("azure")
