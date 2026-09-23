"""Escreve o JSON por teste exigido por CLAUDE.md §9.1 em
`report/tests/<run_id>/<action_id>/<test_id>.json`.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ._common import sha256_bytes


def write_test_json(
    *,
    run_id: str,
    action_id: str,
    test_id: str,
    metric: str,
    backend_llm: str | None,
    test_code_source: str,
    test_code_file: str,
    data_used: dict,
    results: dict,
    report_dir: Path,
    notes: list[str] | None = None,
) -> Path:
    payload = {
        "run_id": run_id,
        "action_id": action_id,
        "test_id": test_id,
        "metric": metric,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "backend_llm": backend_llm,
        "test_code": {
            "source": test_code_source,
            "file": test_code_file,
            "hash": sha256_bytes(test_code_source.encode("utf-8")),
        },
        "data_used": data_used,
        "results": results,
        "notes": notes or [],
    }

    out_dir = report_dir / "tests" / run_id / action_id
    out_dir.mkdir(parents=True, exist_ok=True)
    # test_id pode conter caracteres não seguros para nome de arquivo (ex.: "%")
    safe_test_id = "".join(c if c.isalnum() or c in "_-." else "_" for c in test_id)
    path = out_dir / f"{safe_test_id}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
