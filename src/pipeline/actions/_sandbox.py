"""Execução em sandbox de código gerado pela Action 06 (CLAUDE.md §2.2).

Duas camadas: (1) checagem estática do código-fonte via AST antes de rodar —
rejeita import de rede/SO sem nunca executar o código (§2.2: "Se o agente
detectar isso no código antes de rodar, deve rejeitar e regenerar"); (2)
execução em subprocess isolado, com timeout, cwd próprio (tempdir descartável),
capturando stdout/stderr/exit code (§2.2).
"""

from __future__ import annotations

import ast
import json
import math
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

FORBIDDEN_MODULES = {
    "requests", "urllib", "urllib2", "socket", "http", "httplib",
    "ftplib", "smtplib", "telnetlib", "subprocess", "ssl", "asyncio",
}
FORBIDDEN_OS_CALLS = {"system", "popen", "exec", "execv", "execve", "spawn", "spawnv", "fork"}

DEFAULT_TIMEOUT_SECONDS = 120

_RUNNER_TEMPLATE = """\
import json
import sys

sys.path.insert(0, {module_dir!r})
import {module_name} as _generated_module

with open({input_path!r}, "r", encoding="utf-8") as _f:
    _inputs = json.load(_f)

_result = _generated_module.compute(_inputs["portfolio"], _inputs["risk_factors"], _inputs["params"])

with open({output_path!r}, "w", encoding="utf-8") as _f:
    json.dump(_result, _f)
"""


@dataclass
class SandboxResult:
    accepted: bool
    stdout: str
    stderr: str
    exit_code: int | None
    result: dict | None
    rejection_reason: str | None = None


def check_forbidden_constructs(source: str) -> list[str]:
    """Retorna violações encontradas (lista vazia = seguro para rodar)."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [f"erro de sintaxe: {exc}"]

    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in FORBIDDEN_MODULES:
                    violations.append(f"import proibido: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] in FORBIDDEN_MODULES:
                violations.append(f"import proibido: {node.module}")
        elif isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name) and node.value.id == "os" and node.attr in FORBIDDEN_OS_CALLS:
                violations.append(f"chamada proibida: os.{node.attr}")
        elif isinstance(node, ast.Name) and node.id == "__import__":
            violations.append("uso de __import__ dinâmico proibido")
    return violations


def run_in_sandbox(
    source: str,
    *,
    module_name: str,
    portfolio: dict,
    risk_factors: dict,
    params: dict,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> SandboxResult:
    violations = check_forbidden_constructs(source)
    if violations:
        return SandboxResult(
            accepted=False, stdout="", stderr="", exit_code=None, result=None,
            rejection_reason="; ".join(violations),
        )

    with tempfile.TemporaryDirectory(prefix="claude_metric_sandbox_") as tmpdir:
        tmp_path = Path(tmpdir)
        (tmp_path / f"{module_name}.py").write_text(source, encoding="utf-8")

        input_path = tmp_path / "inputs.json"
        output_path = tmp_path / "output.json"
        input_path.write_text(
            json.dumps({"portfolio": portfolio, "risk_factors": risk_factors, "params": params}), encoding="utf-8"
        )

        runner_path = tmp_path / "_runner.py"
        runner_path.write_text(
            _RUNNER_TEMPLATE.format(
                module_dir=str(tmp_path), module_name=module_name,
                input_path=str(input_path), output_path=str(output_path),
            ),
            encoding="utf-8",
        )

        try:
            proc = subprocess.run(
                [sys.executable, str(runner_path)],
                cwd=str(tmp_path),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            return SandboxResult(
                accepted=False, stdout=exc.stdout or "", stderr=exc.stderr or "",
                exit_code=None, result=None, rejection_reason=f"timeout após {timeout}s",
            )

        if proc.returncode != 0:
            return SandboxResult(
                accepted=False, stdout=proc.stdout, stderr=proc.stderr,
                exit_code=proc.returncode, result=None, rejection_reason="exit code != 0",
            )

        if not output_path.exists():  # pragma: no cover - o runner sempre escreve output.json antes de
            # sair com 0 (só não escreveria sob uma falha externa entre o compute() retornar e o write,
            # ex.: disco cheio — não reproduzível deterministicamente num teste)
            return SandboxResult(
                accepted=False, stdout=proc.stdout, stderr=proc.stderr,
                exit_code=proc.returncode, result=None, rejection_reason="nenhum output.json produzido",
            )

        try:
            result = json.loads(output_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:  # pragma: no cover - json.dump no runner só falha (TypeError)
            # ANTES de qualquer byte ser gravado se o retorno não for serializável, e isso já sai com
            # exit code != 0 (capturado acima) — um output.json corrompido mas presente exigiria
            # interferência externa no arquivo, não reproduzível deterministicamente num teste.
            return SandboxResult(
                accepted=False, stdout=proc.stdout, stderr=proc.stderr,
                exit_code=proc.returncode, result=None, rejection_reason=f"output.json inválido: {exc}",
            )

        if not isinstance(result, dict) or "valor" not in result:
            return SandboxResult(
                accepted=False, stdout=proc.stdout, stderr=proc.stderr,
                exit_code=proc.returncode, result=result if isinstance(result, dict) else None,
                rejection_reason="resultado não é um dict com a chave 'valor'",
            )

        valor = result.get("valor")
        if not isinstance(valor, (int, float)) or isinstance(valor, bool) or not math.isfinite(valor):
            return SandboxResult(
                accepted=False, stdout=proc.stdout, stderr=proc.stderr,
                exit_code=proc.returncode, result=result,
                rejection_reason=f"'valor' não é um número finito: {valor!r}",
            )

        return SandboxResult(
            accepted=True, stdout=proc.stdout, stderr=proc.stderr, exit_code=proc.returncode, result=result,
        )
