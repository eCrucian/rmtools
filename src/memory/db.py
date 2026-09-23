"""Persistência de memória em SQLite local (CLAUDE.md §2.3).

`memory/state.db` é um arquivo único, versionável. As tabelas "de saída
estruturada por action" (extractions, quality_scores, methodology_assessment,
regulatory_adherence, stability_results, backtest_results, extended_tests,
replicability_log) guardam um blob JSON genérico — o schema interno de cada uma
é definido pela action que escreve nela (Action 02..09), não pelo banco; isso
evita reescrever o schema do banco toda vez que uma action evolui seu output.
`decisions_log` é a exceção: tem colunas nomeadas porque é a tabela mais
importante do ponto de vista de auditoria (CLAUDE.md §2.3) e sua estrutura é
fixa e vale a pena consultar por coluna (ex.: `WHERE criticidade = 'alta'`).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_JSON_BLOB_TABLES = (
    "extractions",
    "quality_scores",
    "methodology_assessment",
    "regulatory_adherence",
    "stability_results",
    "backtest_results",
    "extended_tests",
    "replicability_log",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    doc_source TEXT,
    backend_llm TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    created_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    doc_type TEXT NOT NULL,
    is_code_example INTEGER NOT NULL DEFAULT 0,
    sections_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS code_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    action_id TEXT NOT NULL,
    metric TEXT NOT NULL,
    file_path TEXT NOT NULL,
    code_hash TEXT NOT NULL,
    diff TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decisions_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    action_id TEXT NOT NULL,
    campo_afetado TEXT NOT NULL,
    ambiguidade_encontrada TEXT NOT NULL,
    decisao_tomada TEXT NOT NULL,
    justificativa TEXT NOT NULL,
    fonte_da_decisao TEXT NOT NULL,
    criticidade TEXT NOT NULL CHECK (criticidade IN ('baixa', 'media', 'alta')),
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS llm_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    action_id TEXT NOT NULL,
    backend TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_hash TEXT NOT NULL,
    tokens_in INTEGER NOT NULL,
    tokens_out INTEGER NOT NULL,
    latency_ms REAL NOT NULL,
    schema_satisfied INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS action_runs (
    run_id TEXT NOT NULL,
    action_id TEXT NOT NULL,
    status TEXT NOT NULL,
    output_json TEXT NOT NULL,
    artifacts_json TEXT NOT NULL,
    notes_json TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (run_id, action_id)
);
"""

for _table in _JSON_BLOB_TABLES:
    _SCHEMA += f"""
CREATE TABLE IF NOT EXISTS {_table} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    action_id TEXT NOT NULL,
    data_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    return value


class MemoryStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "MemoryStore":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    # -- runs --------------------------------------------------------------

    def start_run(self, run_id: str, doc_source: str | None, backend_llm: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO runs (run_id, doc_source, backend_llm, status, created_at) "
            "VALUES (?, ?, ?, 'running', ?)",
            (run_id, doc_source, backend_llm, _now()),
        )
        self.conn.commit()

    def finish_run(self, run_id: str, status: str) -> None:
        self.conn.execute(
            "UPDATE runs SET status = ?, finished_at = ? WHERE run_id = ?",
            (status, _now(), run_id),
        )
        self.conn.commit()

    def get_run(self, run_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return dict(row) if row else None

    # -- documents -----------------------------------------------------------

    def record_document(
        self,
        run_id: str,
        file_path: str,
        sha256: str,
        doc_type: str,
        is_code_example: bool,
        sections: list[str] | None = None,
    ) -> None:
        self.conn.execute(
            "INSERT INTO documents (run_id, file_path, sha256, doc_type, is_code_example, "
            "sections_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (run_id, file_path, sha256, doc_type, int(is_code_example), json.dumps(sections or []), _now()),
        )
        self.conn.commit()

    # -- decisions_log ---------------------------------------------------------

    def log_decision(
        self,
        run_id: str,
        action_id: str,
        campo_afetado: str,
        ambiguidade_encontrada: str,
        decisao_tomada: str,
        justificativa: str,
        fonte_da_decisao: str,
        criticidade: str,
    ) -> None:
        if criticidade not in ("baixa", "media", "alta"):
            raise ValueError(f"criticidade inválida: {criticidade!r} (esperado baixa/media/alta)")
        self.conn.execute(
            "INSERT INTO decisions_log (run_id, action_id, campo_afetado, ambiguidade_encontrada, "
            "decisao_tomada, justificativa, fonte_da_decisao, criticidade, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                action_id,
                campo_afetado,
                ambiguidade_encontrada,
                decisao_tomada,
                justificativa,
                fonte_da_decisao,
                criticidade,
                _now(),
            ),
        )
        self.conn.commit()

    def get_decisions(self, run_id: str, criticidade: str | None = None) -> list[dict]:
        if criticidade is None:
            rows = self.conn.execute(
                "SELECT * FROM decisions_log WHERE run_id = ? ORDER BY id", (run_id,)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM decisions_log WHERE run_id = ? AND criticidade = ? ORDER BY id",
                (run_id, criticidade),
            ).fetchall()
        return [dict(r) for r in rows]

    # -- llm_calls -------------------------------------------------------------

    def log_llm_call(self, run_id: str, action_id: str, response) -> None:
        self.conn.execute(
            "INSERT INTO llm_calls (run_id, action_id, backend, model, prompt_hash, tokens_in, "
            "tokens_out, latency_ms, schema_satisfied, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                action_id,
                response.backend,
                response.model,
                response.prompt_hash,
                response.tokens_in,
                response.tokens_out,
                response.latency_ms,
                int(response.parsed is not None),
                _now(),
            ),
        )
        self.conn.commit()

    # -- tabelas de saída (blob JSON) -------------------------------------------

    def write_output(self, table: str, run_id: str, action_id: str, data: Any) -> int:
        if table not in _JSON_BLOB_TABLES:
            raise ValueError(f"tabela desconhecida: {table!r} (esperado uma de {_JSON_BLOB_TABLES})")
        cur = self.conn.execute(
            f"INSERT INTO {table} (run_id, action_id, data_json, created_at) VALUES (?, ?, ?, ?)",
            (run_id, action_id, json.dumps(_to_jsonable(data), ensure_ascii=False), _now()),
        )
        self.conn.commit()
        return cur.lastrowid

    def read_outputs(self, table: str, run_id: str) -> list[dict]:
        if table not in _JSON_BLOB_TABLES:
            raise ValueError(f"tabela desconhecida: {table!r} (esperado uma de {_JSON_BLOB_TABLES})")
        rows = self.conn.execute(
            f"SELECT * FROM {table} WHERE run_id = ? ORDER BY id", (run_id,)
        ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["data"] = json.loads(d.pop("data_json"))
            result.append(d)
        return result

    # -- code_versions -----------------------------------------------------

    def record_code_version(
        self, run_id: str, action_id: str, metric: str, file_path: str, code_hash: str, diff: str = ""
    ) -> None:
        self.conn.execute(
            "INSERT INTO code_versions (run_id, action_id, metric, file_path, code_hash, diff, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (run_id, action_id, metric, file_path, code_hash, diff, _now()),
        )
        self.conn.commit()

    # -- action_runs (checkpoint/resumabilidade, §2.3) --------------------------

    def save_action_result(self, run_id: str, action_id: str, input_hash: str, result) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO action_runs (run_id, action_id, status, output_json, "
            "artifacts_json, notes_json, input_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                action_id,
                result.status,
                json.dumps(_to_jsonable(result.output), ensure_ascii=False),
                json.dumps([str(p) for p in result.artifacts], ensure_ascii=False),
                json.dumps(result.notes, ensure_ascii=False),
                input_hash,
                _now(),
            ),
        )
        self.conn.commit()

    def get_checkpoint(self, run_id: str, action_id: str, input_hash: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM action_runs WHERE run_id = ? AND action_id = ? AND input_hash = ?",
            (run_id, action_id, input_hash),
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["output"] = json.loads(d.pop("output_json"))
        d["artifacts"] = json.loads(d.pop("artifacts_json"))
        d["notes"] = json.loads(d.pop("notes_json"))
        return d

    def get_all_action_runs(self, run_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM action_runs WHERE run_id = ? ORDER BY created_at", (run_id,)
        ).fetchall()
        out = []
        for row in rows:
            d = dict(row)
            d["output"] = json.loads(d.pop("output_json"))
            d["artifacts"] = json.loads(d.pop("artifacts_json"))
            d["notes"] = json.loads(d.pop("notes_json"))
            out.append(d)
        return out
