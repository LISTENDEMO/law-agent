from __future__ import annotations

import json
import secrets
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException

from app.evaluation.runner import generate_open_ended_dataset
from app.storage.repository import Repository


def create_admin_router(
    admin_api_key: str,
    repository: Repository,
    *,
    data_dir: str | Path,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/admin")
    data_path = Path(data_dir)

    def require_admin(x_admin_key: str) -> None:
        if not admin_api_key or not secrets.compare_digest(x_admin_key, admin_api_key):
            raise HTTPException(status_code=401, detail="invalid admin credentials")

    @router.get("/corpus/report")
    def corpus_report(x_admin_key: str = Header(default="")) -> dict[str, object]:
        require_admin(x_admin_key)
        return _corpus_status(data_path)

    @router.get("/overview")
    def overview(x_admin_key: str = Header(default="")) -> dict[str, object]:
        require_admin(x_admin_key)
        open_cases = generate_open_ended_dataset()
        return {
            "corpus": _corpus_status(data_path),
            "index": _index_status(data_path),
            "recent_runs": repository.list_recent_runs(limit=10),
            "evaluation": {
                "open_ended_case_count": len(open_cases),
                "categories": sorted({case.category for case in open_cases}),
            },
        }

    return router


def _corpus_status(data_dir: Path) -> dict[str, object]:
    report_path = data_dir / "reports" / "corpus.json"
    if not report_path.exists():
        return {"status": "missing", "report_url": "/data/reports/corpus.json"}
    try:
        report = json.loads(report_path.read_text("utf-8"))
    except json.JSONDecodeError:
        return {"status": "invalid", "report_url": "/data/reports/corpus.json"}
    return {"status": "available", "report_url": "/data/reports/corpus.json", "report": report}


def _index_status(data_dir: Path) -> dict[str, object]:
    metadata_path = data_dir / "indexes" / "law" / "metadata.json"
    if not metadata_path.exists():
        return {"status": "missing", "metadata": None}
    try:
        metadata = json.loads(metadata_path.read_text("utf-8"))
    except json.JSONDecodeError:
        return {"status": "invalid", "metadata": None}
    return {"status": "available", "metadata": metadata}
