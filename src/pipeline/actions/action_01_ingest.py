"""Action 01 — Ingestão de documentação (CLAUDE.md §Action 01)."""

from __future__ import annotations

import json
from pathlib import Path

from src.pipeline.contracts import ActionResult, RunContext

from ._common import CODE_EXAMPLE_EXTENSIONS, METHODOLOGY_EXTENSIONS, sha256_bytes

ACTION_ID = "01_ingest_documentation"

_OPTIONAL_EXTRACTORS_NOTE = (
    "extração de texto de '{ext}' requer uma lib opcional não instalada neste "
    "ambiente ({lib}); o arquivo foi registrado mas seu conteúdo não entrou no "
    "texto metodológico desta run"
)


def _extract_docx(path: Path) -> str | None:
    try:
        import docx  # type: ignore
    except ImportError:
        return None
    document = docx.Document(str(path))
    return "\n".join(p.text for p in document.paragraphs)


def _extract_pdf(path: Path) -> str | None:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        return None
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_ipynb(path: Path) -> str:
    notebook = json.loads(path.read_text(encoding="utf-8"))
    parts = []
    for cell in notebook.get("cells", []):
        source = cell.get("source", "")
        parts.append("".join(source) if isinstance(source, list) else str(source))
    return "\n\n".join(parts)


def run(ctx: RunContext) -> ActionResult:
    doc_paths = ctx.inputs.get("doc_paths") or []

    if not doc_paths:
        ctx.memory.log_decision(
            run_id=ctx.run_id,
            action_id=ACTION_ID,
            campo_afetado="documento_de_entrada",
            ambiguidade_encontrada="Nenhum arquivo de documentação foi fornecido para esta run.",
            decisao_tomada="Pipeline prossegue sem texto metodológico; ações subsequentes tratam a ausência.",
            justificativa="A regra §6/§8 exige que o pipeline nunca trave, mesmo sem input.",
            fonte_da_decisao="assunção conservadora",
            criticidade="alta",
        )
        return ActionResult(
            status="needs_human_review",
            output={"methodological_text": "", "documents": [], "has_code_example": False},
            notes=["Nenhum documento fornecido para ingestão."],
        )

    methodological_chunks: list[str] = []
    documents_meta: list[dict] = []
    has_code_example = False
    notes: list[str] = []

    for raw_path in doc_paths:
        path = Path(raw_path)
        ext = path.suffix.lower()
        data = path.read_bytes()
        digest = sha256_bytes(data)
        is_code_example = ext in CODE_EXAMPLE_EXTENSIONS

        text: str | None
        if ext in (".md", ".txt"):
            text = data.decode("utf-8", errors="replace")
        elif ext == ".ipynb":
            text = _extract_ipynb(path)
        elif ext == ".docx":
            text = _extract_docx(path)
            if text is None:
                notes.append(_OPTIONAL_EXTRACTORS_NOTE.format(ext=ext, lib="python-docx"))
        elif ext == ".pdf":
            text = _extract_pdf(path)
            if text is None:
                notes.append(_OPTIONAL_EXTRACTORS_NOTE.format(ext=ext, lib="pypdf"))
        elif ext in (".py", ".csv"):
            text = data.decode("utf-8", errors="replace")
        elif ext == ".xlsx":
            text = None
            notes.append(f"planilha '{path.name}' registrada como anexo; conteúdo tabular não extraído nesta fase")
        else:
            text = None
            notes.append(f"extensão '{ext}' não suportada — arquivo '{path.name}' ignorado")

        documents_meta.append(
            {"file_path": str(path), "sha256": digest, "doc_type": ext, "is_code_example": is_code_example}
        )
        ctx.memory.record_document(
            run_id=ctx.run_id,
            file_path=str(path),
            sha256=digest,
            doc_type=ext,
            is_code_example=is_code_example,
        )

        if is_code_example:
            has_code_example = True
            # Regra crítica (§6.1): texto de código/planilha de exemplo NUNCA entra
            # no texto metodológico repassado à Action 02/06 — fica só registrado
            # em `documents` (acima) para uso posterior e isolado pela Action 10-b.
            continue

        if ext in METHODOLOGY_EXTENSIONS and text:
            methodological_chunks.append(f"## Fonte: {path.name}\n\n{text}")

    methodological_text = "\n\n".join(methodological_chunks)
    if not methodological_text.strip():
        ctx.memory.log_decision(
            run_id=ctx.run_id,
            action_id=ACTION_ID,
            campo_afetado="texto_metodologico",
            ambiguidade_encontrada="Nenhum texto metodológico pôde ser extraído dos documentos fornecidos.",
            decisao_tomada="Pipeline prossegue com texto metodológico vazio.",
            justificativa="Arquivos fornecidos eram só anexos de código/planilha, ou libs opcionais de extração ausentes.",
            fonte_da_decisao="assunção conservadora",
            criticidade="alta",
        )
        status = "needs_human_review"
        notes.append("Nenhum texto metodológico extraído — só anexos de código/planilha ou extração indisponível.")
    else:
        status = "success"

    return ActionResult(
        status=status,
        output={
            "methodological_text": methodological_text,
            "documents": documents_meta,
            "has_code_example": has_code_example,
        },
        notes=notes,
    )
