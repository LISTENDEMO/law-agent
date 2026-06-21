from __future__ import annotations

import json
from pathlib import Path

from app.corpus.parser import parse_docx
from app.domain.models import CorpusIssue, CorpusReport


def ingest_corpus(
    corpus_dir: str | Path,
    normalized_path: str | Path,
    report_path: str | Path,
) -> CorpusReport:
    source_dir = Path(corpus_dir)
    normalized_target = Path(normalized_path)
    report_target = Path(report_path)
    candidates = (
        path
        for path in source_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in {".doc", ".docx"}
    )
    files = sorted(candidates, key=lambda path: path.name)

    records: list[dict[str, object]] = []
    issues: list[CorpusIssue] = []
    seen_content: dict[str, str] = {}
    accepted = 0
    duplicates = 0
    quarantined = 0

    for path in files:
        relative_name = path.relative_to(source_dir).as_posix()
        if path.suffix.lower() == ".doc":
            quarantined += 1
            issues.append(
                CorpusIssue(
                    source_file=relative_name,
                    code="unsupported_doc",
                    message="旧版 DOC 需要转换为 DOCX 后再导入",
                )
            )
            continue
        try:
            document = parse_docx(path)
        except Exception as error:
            quarantined += 1
            issues.append(
                CorpusIssue(
                    source_file=relative_name,
                    code="parse_error",
                    message=f"{type(error).__name__}: 无法解析文档",
                )
            )
            continue

        duplicate_of = seen_content.get(document.content_hash)
        if duplicate_of is not None:
            duplicates += 1
            issues.append(
                CorpusIssue(
                    source_file=relative_name,
                    code="duplicate_content",
                    message=f"规范化正文与 {duplicate_of} 重复",
                )
            )
            continue

        seen_content[document.content_hash] = relative_name
        accepted += 1
        records.extend(article.model_dump(mode="json") for article in document.articles)

    report = CorpusReport(
        total_files=len(files),
        accepted=accepted,
        duplicates=duplicates,
        quarantined=quarantined,
        article_count=len(records),
        issues=issues,
    )
    _write_jsonl_atomic(normalized_target, records)
    _write_json_atomic(report_target, report.model_dump(mode="json"))
    return report


def _write_jsonl_atomic(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    content = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def _write_json_atomic(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)
