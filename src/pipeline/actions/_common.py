"""Helpers compartilhados entre módulos de action. Não é uma action em si."""

from __future__ import annotations

import hashlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PROMPTS_DIR = REPO_ROOT / "prompts"
DATA_DIR = REPO_ROOT / "data"
CONFIG_DIR = REPO_ROOT / "config"
REPORT_DIR = REPO_ROOT / "report"

# Extensões tratadas como "código/planilha de exemplo anexado" (CLAUDE.md §6.1):
# NUNCA entram no prompt de geração de código da Action 06.
CODE_EXAMPLE_EXTENSIONS = {".py", ".xlsx", ".csv"}
# Extensões tratadas como "texto metodológico" (alimenta Action 02 e Action 06).
METHODOLOGY_EXTENSIONS = {".md", ".docx", ".ipynb", ".pdf", ".txt"}


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def load_prompt_template(action_id: str, filename: str) -> str:
    path = PROMPTS_DIR / action_id / filename
    return path.read_text(encoding="utf-8")


def frozen_portfolio_available() -> bool:
    """§5.3: dados de mercado/carteira base congelados uma única vez em data/.
    Enquanto não forem gerados (fase 2), actions que dependem deles devem
    reconhecer a ausência explicitamente em vez de fabricar resultado."""
    risk_factors_dir = DATA_DIR / "risk_factors"
    if not risk_factors_dir.exists():
        return False
    return any(risk_factors_dir.glob("*.csv"))
