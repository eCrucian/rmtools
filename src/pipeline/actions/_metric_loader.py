"""Import dinâmico de um módulo de métrica já aceito pela Action 06.

Diferente da Action 06 (que roda código ainda NÃO vetado em sandbox isolado,
com checagem estática prévia), este loader só é usado sobre módulos que já
passaram pelas duas camadas de defesa de `_sandbox.py` e foram escritos em
disco como aceitos — por isso Actions 07/08 importam e chamam `compute`
diretamente no processo (muito mais rápido que resandboxar a cada choque),
em vez de reabrir um subprocess por teste de estabilidade/backtest.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Callable


def load_compute_function(module_path: str | Path, module_name: str) -> Callable[[dict, dict, dict], dict]:
    path = Path(module_path)
    if not path.exists():
        raise FileNotFoundError(f"módulo de métrica não encontrado: {path}")

    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"não foi possível carregar o módulo em {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    compute = getattr(module, "compute", None)
    if compute is None or not callable(compute):
        raise AttributeError(f"módulo em {path} não define uma função `compute` chamável")
    return compute
