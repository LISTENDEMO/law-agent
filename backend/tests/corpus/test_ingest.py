from __future__ import annotations

import json
from pathlib import Path

from app.corpus.ingest import ingest_corpus
from docx import Document


def _write_docx(path: Path, paragraphs: list[str]) -> None:
    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    document.save(path)


def test_ingest_writes_articles_and_machine_readable_report(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    _write_docx(corpus / "示例法_20250101.docx", ["示例法", "第一条 示例内容。"])
    normalized = tmp_path / "normalized.jsonl"
    report_path = tmp_path / "report.json"

    report = ingest_corpus(corpus, normalized, report_path)

    records = [json.loads(line) for line in normalized.read_text("utf-8").splitlines()]
    persisted_report = json.loads(report_path.read_text("utf-8"))
    assert report.accepted == 1
    assert report.article_count == 1
    assert records[0]["law_name"] == "示例法"
    assert persisted_report["total_files"] == 1


def test_ingest_deduplicates_normalized_document_content(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    content = ["示例条例", "第一条 完全相同的内容。"]
    _write_docx(corpus / "示例条例_20240101.docx", content)
    _write_docx(corpus / "示例条例-20240101.docx", content)

    report = ingest_corpus(corpus, tmp_path / "normalized.jsonl", tmp_path / "report.json")

    assert report.total_files == 2
    assert report.accepted == 1
    assert report.duplicates == 1
    assert any(issue.code == "duplicate_content" for issue in report.issues)


def test_ingest_quarantines_legacy_doc_and_broken_docx(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "旧法规.doc").write_bytes(b"legacy-binary")
    (corpus / "损坏法规.docx").write_text("not a zip", encoding="utf-8")

    report = ingest_corpus(corpus, tmp_path / "normalized.jsonl", tmp_path / "report.json")

    assert report.quarantined == 2
    assert {issue.code for issue in report.issues} == {"unsupported_doc", "parse_error"}
