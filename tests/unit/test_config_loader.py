from __future__ import annotations

from src.pipeline import config as config_mod
from src.pipeline.actions._common import CONFIG_DIR


def test_load_real_extended_tests_yaml_with_pyyaml():
    data = config_mod.load_yaml(CONFIG_DIR / "extended_tests.yaml")
    ids = {t["id"] for t in data["extended_tests"]}
    assert ids == {"concentration_test", "liquidity_horizon_scaling"}
    assert all(t["enabled"] is True for t in data["extended_tests"])


def test_load_real_stability_bounds_yaml_with_pyyaml():
    data = config_mod.load_yaml(CONFIG_DIR / "stability_bounds.yaml")
    assert data["stability"]["choques_pct"] == [0.001, 0.01, 0.05, 0.10, 0.25]
    assert data["backtest"]["holding_periods"] == [1, 10, 30, 60, 90, 180]


def test_minimal_yaml_fallback_matches_pyyaml_on_extended_tests(monkeypatch, tmp_path):
    monkeypatch.setattr(config_mod, "_HAS_YAML", False)
    data = config_mod.load_yaml(CONFIG_DIR / "extended_tests.yaml")
    ids = {t["id"] for t in data["extended_tests"]}
    assert ids == {"concentration_test", "liquidity_horizon_scaling"}
    assert data["extended_tests"][0]["enabled"] is True
    assert "concentração" in data["extended_tests"][0]["description"]


def test_minimal_yaml_fallback_matches_pyyaml_on_stability_bounds(monkeypatch):
    monkeypatch.setattr(config_mod, "_HAS_YAML", False)
    data = config_mod.load_yaml(CONFIG_DIR / "stability_bounds.yaml")
    assert data["stability"]["choques_pct"] == [0.001, 0.01, 0.05, 0.1, 0.25]
    assert data["backtest"]["holding_periods"] == [1, 10, 30, 60, 90, 180]
    assert data["backtest"]["overlapping_windows"] is True


def test_scalar_parsing_edge_cases():
    assert config_mod._scalar("null") is None
    assert config_mod._scalar("~") is None
    assert config_mod._scalar("true") is True
    assert config_mod._scalar("false") is False
    assert config_mod._scalar('"quoted"') == "quoted"
    assert config_mod._scalar("'single'") == "single"
    assert config_mod._scalar("[1, 2, 3]") == [1, 2, 3]
    assert config_mod._scalar("[]") == []
    assert config_mod._scalar("{a: 1, b: 2}") == {"a": 1, "b": 2}
    assert config_mod._scalar("42") == 42
    assert config_mod._scalar("3.14") == 3.14
    assert config_mod._scalar("texto_livre") == "texto_livre"


def test_minimal_yaml_load_flat_mapping(tmp_path):
    path = tmp_path / "flat.yaml"
    path.write_text("a: 1\nb: texto\nc: true\n", encoding="utf-8")
    assert config_mod._minimal_yaml_load(path.read_text(encoding="utf-8")) == {"a": 1, "b": "texto", "c": True}


def test_minimal_yaml_load_key_with_empty_value_and_no_nested_block():
    text = "a:\nb: 2\n"
    assert config_mod._minimal_yaml_load(text) == {"a": None, "b": 2}


def test_minimal_yaml_load_multiline_list_of_scalars():
    text = "holding_periods:\n  - 1\n  - 10\n  - 30\n"
    assert config_mod._minimal_yaml_load(text) == {"holding_periods": [1, 10, 30]}


def test_minimal_yaml_load_list_item_with_nested_mapping():
    text = "items:\n  - outer:\n    subkey: 1\n    other: dois\n"
    parsed = config_mod._minimal_yaml_load(text)
    assert parsed == {"items": [{"outer": {"subkey": 1, "other": "dois"}}]}


def test_strip_inline_comment_respects_quotes():
    assert config_mod._strip_inline_comment("a: 1  # comentário") == "a: 1  "
    assert config_mod._strip_inline_comment("a: 'texto # não é comentário'") == "a: 'texto # não é comentário'"
    assert config_mod._strip_inline_comment('a: "outro # também não"') == 'a: "outro # também não"'
    assert config_mod._strip_inline_comment("sem comentário nenhum") == "sem comentário nenhum"
