from __future__ import annotations

import secrets

from fastapi import APIRouter, Header, HTTPException


def create_admin_router(admin_api_key: str) -> APIRouter:
    router = APIRouter(prefix="/api/v1/admin")

    @router.get("/corpus/report")
    def corpus_report(x_admin_key: str = Header(default="")) -> dict[str, object]:
        if not admin_api_key or not secrets.compare_digest(x_admin_key, admin_api_key):
            raise HTTPException(status_code=401, detail="invalid admin credentials")
        return {"status": "available", "report_url": "/data/reports/corpus.json"}

    return router

