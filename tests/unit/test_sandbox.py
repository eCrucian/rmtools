from __future__ import annotations

from src.pipeline.actions import _sandbox as sb

# --------------------------------------------------------------------------
# check_forbidden_constructs (checagem estática, sem rodar nada)
# --------------------------------------------------------------------------

def test_safe_code_has_no_violations():
    source = "import math\n\ndef compute(portfolio, risk_factors, params):\n    return {'valor': math.sqrt(4)}\n"
    assert sb.check_forbidden_constructs(source) == []


def test_flags_plain_import_requests():
    violations = sb.check_forbidden_constructs("import requests\n")
    assert any("requests" in v for v in violations)


def test_flags_submodule_import():
    violations = sb.check_forbidden_constructs("import urllib.request\n")
    assert any("urllib" in v for v in violations)


def test_flags_from_import_socket():
    violations = sb.check_forbidden_constructs("from socket import socket\n")
    assert any("socket" in v for v in violations)


def test_flags_os_system_call():
    violations = sb.check_forbidden_constructs("import os\nos.system('echo hi')\n")
    assert any("os.system" in v for v in violations)


def test_flags_dynamic_import():
    violations = sb.check_forbidden_constructs("m = __import__('os')\n")
    assert any("__import__" in v for v in violations)


def test_flags_syntax_error():
    violations = sb.check_forbidden_constructs("def compute(:\n")
    assert any("sintaxe" in v for v in violations)


def test_os_path_join_is_not_flagged():
    violations = sb.check_forbidden_constructs("import os\nx = os.path.join('a', 'b')\n")
    assert violations == []


def test_relative_import_without_module_name_is_not_flagged():
    # `from . import x` tem ast.ImportFrom.module == None — não deve quebrar
    # a checagem nem ser confundido com um import proibido.
    violations = sb.check_forbidden_constructs("from . import algo\n")
    assert violations == []


# --------------------------------------------------------------------------
# run_in_sandbox (execução real em subprocess isolado)
# --------------------------------------------------------------------------

def test_forbidden_import_is_rejected_without_running():
    result = sb.run_in_sandbox(
        "import socket\ndef compute(portfolio, risk_factors, params):\n    return {'valor': 1.0}\n",
        module_name="m", portfolio={}, risk_factors={}, params={},
    )
    assert result.accepted is False
    assert "proibido" in result.rejection_reason
    assert result.exit_code is None  # nunca chegou a rodar


def test_valid_metric_is_accepted():
    source = "def compute(portfolio, risk_factors, params):\n    return {'valor': portfolio['value'] * params['fator']}\n"
    result = sb.run_in_sandbox(
        source, module_name="m", portfolio={"value": 100.0}, risk_factors={"returns": []}, params={"fator": 2.0},
    )
    assert result.accepted is True
    assert result.result["valor"] == 200.0
    assert result.exit_code == 0


def test_uses_risk_factors_returns():
    source = (
        "def compute(portfolio, risk_factors, params):\n"
        "    return {'valor': sum(risk_factors['returns']) / len(risk_factors['returns'])}\n"
    )
    result = sb.run_in_sandbox(
        source, module_name="m", portfolio={"value": 1.0}, risk_factors={"returns": [0.01, 0.02, 0.03]}, params={},
    )
    assert result.accepted is True
    assert abs(result.result["valor"] - 0.02) < 1e-9


def test_exception_in_generated_code_is_rejected():
    source = "def compute(portfolio, risk_factors, params):\n    raise ValueError('bug proposital')\n"
    result = sb.run_in_sandbox(source, module_name="m", portfolio={}, risk_factors={}, params={})
    assert result.accepted is False
    assert result.exit_code != 0
    assert "bug proposital" in result.stderr


def test_missing_compute_function_is_rejected():
    source = "def outra_coisa():\n    return 1\n"
    result = sb.run_in_sandbox(source, module_name="m", portfolio={}, risk_factors={}, params={})
    assert result.accepted is False
    assert result.exit_code != 0


def test_non_dict_return_is_rejected():
    source = "def compute(portfolio, risk_factors, params):\n    return [1, 2, 3]\n"
    result = sb.run_in_sandbox(source, module_name="m", portfolio={}, risk_factors={}, params={})
    assert result.accepted is False
    assert "dict" in result.rejection_reason


def test_missing_valor_key_is_rejected():
    source = "def compute(portfolio, risk_factors, params):\n    return {'outro_campo': 1.0}\n"
    result = sb.run_in_sandbox(source, module_name="m", portfolio={}, risk_factors={}, params={})
    assert result.accepted is False
    assert "dict" in result.rejection_reason


def test_nan_valor_is_rejected():
    source = "def compute(portfolio, risk_factors, params):\n    return {'valor': float('nan')}\n"
    result = sb.run_in_sandbox(source, module_name="m", portfolio={}, risk_factors={}, params={})
    assert result.accepted is False
    assert "finito" in result.rejection_reason


def test_infinite_valor_is_rejected():
    source = "def compute(portfolio, risk_factors, params):\n    return {'valor': float('inf')}\n"
    result = sb.run_in_sandbox(source, module_name="m", portfolio={}, risk_factors={}, params={})
    assert result.accepted is False
    assert "finito" in result.rejection_reason


def test_string_valor_is_rejected():
    source = "def compute(portfolio, risk_factors, params):\n    return {'valor': 'não é número'}\n"
    result = sb.run_in_sandbox(source, module_name="m", portfolio={}, risk_factors={}, params={})
    assert result.accepted is False
    assert "finito" in result.rejection_reason


def test_boolean_valor_is_rejected():
    source = "def compute(portfolio, risk_factors, params):\n    return {'valor': True}\n"
    result = sb.run_in_sandbox(source, module_name="m", portfolio={}, risk_factors={}, params={})
    assert result.accepted is False


def test_timeout_is_enforced():
    source = "import time\ndef compute(portfolio, risk_factors, params):\n    time.sleep(5)\n    return {'valor': 1.0}\n"
    result = sb.run_in_sandbox(source, module_name="m", portfolio={}, risk_factors={}, params={}, timeout=1)
    assert result.accepted is False
    assert "timeout" in result.rejection_reason
