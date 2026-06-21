from __future__ import annotations

from pathlib import Path

import pytest
from app.corpus.parser import parse_docx
from docx import Document


def _write_docx(path: Path, paragraphs: list[str]) -> None:
    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    document.save(path)


def test_parse_docx_splits_articles_and_preserves_context(tmp_path: Path) -> None:
    path = tmp_path / "中华人民共和国示例法_20250101.docx"
    _write_docx(
        path,
        [
            "中华人民共和国示例法",
            "第一章 总则",
            "第一条 为了规范示例活动，制定本法。",
            "第二条 在中华人民共和国境内从事示例活动，适用本法。",
            "第二款 特别情形依照有关规定处理。",
        ],
    )

    result = parse_docx(path)

    assert result.law_name == "中华人民共和国示例法"
    assert result.source_date.isoformat() == "2025-01-01"
    assert [article.article_number for article in result.articles] == ["第一条", "第二条"]
    assert result.articles[1].context_path == ["第一章 总则"]
    assert "第二款" in result.articles[1].content
    assert result.articles[0].parse_mode == "article"


def test_parse_docx_produces_stable_article_ids(tmp_path: Path) -> None:
    path = tmp_path / "示例条例-20240102.docx"
    _write_docx(path, ["示例条例", "第一条 条文内容。"])

    first = parse_docx(path)
    second = parse_docx(path)

    assert first.document_id == second.document_id
    assert first.articles[0].article_id == second.articles[0].article_id


def test_parse_docx_uses_fallback_for_unstructured_content(tmp_path: Path) -> None:
    path = tmp_path / "通知.docx"
    _write_docx(path, ["关于示例事项的通知", "这是一段没有法条编号但需要检索的正文。"])

    result = parse_docx(path)

    assert len(result.articles) == 1
    assert result.articles[0].parse_mode == "fallback"
    assert "需要检索" in result.articles[0].content


def test_parse_docx_rejects_empty_document(tmp_path: Path) -> None:
    path = tmp_path / "空文档.docx"
    _write_docx(path, ["", "   "])

    with pytest.raises(ValueError, match="没有可解析的正文"):
        parse_docx(path)
