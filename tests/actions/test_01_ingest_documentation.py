from __future__ import annotations

import json
import sys
import types

from src.pipeline.actions import action_01_ingest
from tests.conftest import make_ctx


def test_no_doc_paths_needs_human_review(memory, fake_llm):
    ctx = make_ctx(memory, fake_llm, inputs={"doc_paths": []})
    result = action_01_ingest.run(ctx)

    assert result.status == "needs_human_review"
    assert result.output["methodological_text"] == ""
    decisions = memory.get_decisions("run_test")
    assert any(d["criticidade"] == "alta" for d in decisions)


def test_md_file_extracts_methodological_text(memory, fake_llm, tmp_path):
    doc = tmp_path / "modelo.md"
    doc.write_text("# VaR paramétrico\n\nFórmula: VaR = z * sigma * sqrt(t)", encoding="utf-8")

    ctx = make_ctx(memory, fake_llm, inputs={"doc_paths": [str(doc)]})
    result = action_01_ingest.run(ctx)

    assert result.status == "success"
    assert "VaR paramétrico" in result.output["methodological_text"]
    assert result.output["has_code_example"] is False


def test_py_file_never_enters_methodological_text(memory, fake_llm, tmp_path):
    """Regra crítica §6.1: código/planilha de exemplo anexado nunca entra no
    texto metodológico repassado à Action 02/06."""
    md = tmp_path / "modelo.md"
    md.write_text("Especificação em texto puro.", encoding="utf-8")
    code = tmp_path / "exemplo_implementacao_secreta.py"
    code.write_text("SEGREDO_QUE_NAO_PODE_VAZAR = 42", encoding="utf-8")

    ctx = make_ctx(memory, fake_llm, inputs={"doc_paths": [str(md), str(code)]})
    result = action_01_ingest.run(ctx)

    assert result.status == "success"
    assert "SEGREDO_QUE_NAO_PODE_VAZAR" not in result.output["methodological_text"]
    assert result.output["has_code_example"] is True
    docs = [d for d in result.output["documents"] if d["is_code_example"]]
    assert len(docs) == 1
    assert docs[0]["file_path"].endswith(".py")


def test_csv_attachment_is_code_example(memory, fake_llm, tmp_path):
    csv_path = tmp_path / "exemplo.csv"
    csv_path.write_text("a,b\n1,2\n", encoding="utf-8")

    ctx = make_ctx(memory, fake_llm, inputs={"doc_paths": [str(csv_path)]})
    result = action_01_ingest.run(ctx)

    assert result.output["has_code_example"] is True
    assert result.output["methodological_text"] == ""
    assert result.status == "needs_human_review"


def test_unsupported_extension_is_noted(memory, fake_llm, tmp_path):
    weird = tmp_path / "arquivo.bin"
    weird.write_bytes(b"\x00\x01\x02")

    ctx = make_ctx(memory, fake_llm, inputs={"doc_paths": [str(weird)]})
    result = action_01_ingest.run(ctx)

    assert any("não suportada" in note for note in result.notes)


def test_docx_without_optional_lib_is_noted(memory, fake_llm, tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "docx", None)  # força ImportError real no `import docx`
    docx = tmp_path / "modelo.docx"
    docx.write_bytes(b"not a real docx")

    ctx = make_ctx(memory, fake_llm, inputs={"doc_paths": [str(docx)]})
    result = action_01_ingest.run(ctx)

    assert result.status == "needs_human_review"
    assert any("python-docx" in note for note in result.notes)


def test_pdf_without_optional_lib_is_noted(memory, fake_llm, tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "pypdf", None)  # força ImportError real no `from pypdf import ...`
    pdf = tmp_path / "modelo.pdf"
    pdf.write_bytes(b"%PDF-1.4 not a real pdf")

    ctx = make_ctx(memory, fake_llm, inputs={"doc_paths": [str(pdf)]})
    result = action_01_ingest.run(ctx)

    assert result.status == "needs_human_review"
    assert any("pypdf" in note for note in result.notes)


def test_extract_docx_returns_none_when_lib_missing(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "docx", None)
    assert action_01_ingest._extract_docx(tmp_path / "qualquer.docx") is None


def test_extract_pdf_returns_none_when_lib_missing(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "pypdf", None)
    assert action_01_ingest._extract_pdf(tmp_path / "qualquer.pdf") is None


def test_ipynb_extracts_cell_sources(memory, fake_llm, tmp_path):
    notebook = {
        "cells": [
            {"cell_type": "markdown", "source": ["# Título\n", "Descrição do modelo."]},
            {"cell_type": "code", "source": "x = 1"},
        ]
    }
    nb_path = tmp_path / "modelo.ipynb"
    nb_path.write_text(json.dumps(notebook), encoding="utf-8")

    ctx = make_ctx(memory, fake_llm, inputs={"doc_paths": [str(nb_path)]})
    result = action_01_ingest.run(ctx)

    assert result.status == "success"
    assert "Descrição do modelo." in result.output["methodological_text"]


def test_docx_with_optional_lib_available_extracts_text(memory, fake_llm, tmp_path, monkeypatch):
    fake_docx = types.ModuleType("docx")

    class _FakeParagraph:
        def __init__(self, text):
            self.text = text

    class _FakeDocument:
        def __init__(self, path):
            self.paragraphs = [_FakeParagraph("Especificação do modelo VaR em docx.")]

    fake_docx.Document = _FakeDocument
    monkeypatch.setitem(sys.modules, "docx", fake_docx)

    docx_path = tmp_path / "modelo.docx"
    docx_path.write_bytes(b"conteudo binario qualquer")

    ctx = make_ctx(memory, fake_llm, inputs={"doc_paths": [str(docx_path)]})
    result = action_01_ingest.run(ctx)

    assert result.status == "success"
    assert "Especificação do modelo VaR em docx." in result.output["methodological_text"]


def test_pdf_with_optional_lib_available_extracts_text(memory, fake_llm, tmp_path, monkeypatch):
    fake_pypdf = types.ModuleType("pypdf")

    class _FakePage:
        def extract_text(self):
            return "Especificação do modelo VaR em pdf."

    class _FakePdfReader:
        def __init__(self, path):
            self.pages = [_FakePage()]

    fake_pypdf.PdfReader = _FakePdfReader
    monkeypatch.setitem(sys.modules, "pypdf", fake_pypdf)

    pdf_path = tmp_path / "modelo.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 conteudo qualquer")

    ctx = make_ctx(memory, fake_llm, inputs={"doc_paths": [str(pdf_path)]})
    result = action_01_ingest.run(ctx)

    assert result.status == "success"
    assert "Especificação do modelo VaR em pdf." in result.output["methodological_text"]


def test_xlsx_registered_without_content(memory, fake_llm, tmp_path):
    xlsx = tmp_path / "exemplo.xlsx"
    xlsx.write_bytes(b"not a real xlsx")

    ctx = make_ctx(memory, fake_llm, inputs={"doc_paths": [str(xlsx)]})
    result = action_01_ingest.run(ctx)

    assert result.output["has_code_example"] is True
    assert any("planilha" in note for note in result.notes)
