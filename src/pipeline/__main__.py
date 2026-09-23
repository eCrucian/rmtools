"""CLI: `python -m src.pipeline --doc caminho/doc.md [--doc outro.py] [--run-id X] [--force]`.

Backend selecionado via env var LLM_BACKEND (default: ollama — CLAUDE.md §10:
"Comece sempre validando o plumbing do pipeline com LLM_BACKEND=ollama... antes
de rodar a run 'de verdade' com LLM_BACKEND=azure").
"""

from __future__ import annotations

import argparse
import sys
import uuid

from src.llm.client import get_llm_client
from src.memory.db import MemoryStore
from src.pipeline.run import run_pipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Roda o pipeline de validação de métricas de risco.")
    parser.add_argument("--doc", action="append", dest="doc_paths", default=[], help="arquivo de documentação (repetível)")
    parser.add_argument("--norm", dest="norm_path", default=None, help="arquivo com o texto da norma (Action 05)")
    parser.add_argument("--run-id", dest="run_id", default=None)
    parser.add_argument("--db", dest="db_path", default="memory/state.db")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    run_id = args.run_id or f"run_{uuid.uuid4().hex[:12]}"
    llm_client = get_llm_client()

    norm_text = None
    if args.norm_path:
        from pathlib import Path

        norm_text = Path(args.norm_path).read_text(encoding="utf-8")

    with MemoryStore(args.db_path) as memory:
        results = run_pipeline(
            run_id=run_id,
            memory=memory,
            llm_client=llm_client,
            inputs={"doc_paths": args.doc_paths, "norm_text": norm_text},
            force=args.force,
        )

    print(f"run_id={run_id} backend={llm_client.backend}")
    for action_id, result in results.items():
        print(f"  {action_id}: {result.status}  {'; '.join(result.notes)}")
    return 0


if __name__ == "__main__":  # pragma: no cover - só roda via `python -m`, não sob pytest
    sys.exit(main())
