from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse, HTMLResponse


router = APIRouter(tags=["public-docs"])

DOCS_DIR = Path(__file__).resolve().parents[3] / "docs" / "public_api"
INDEX_PATH = DOCS_DIR / "index.html"
OPENAPI_PATH = DOCS_DIR / "openapi.yaml"


def _ensure_path(path: Path) -> Path:
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Docs asset not found")
    return path


@router.get("/docs", include_in_schema=False)
def serve_public_docs() -> HTMLResponse:
    path = _ensure_path(INDEX_PATH)
    return HTMLResponse(path.read_text(encoding="utf-8"))


@router.get("/openapi.yaml", include_in_schema=False)
def serve_openapi_yaml() -> FileResponse:
    path = _ensure_path(OPENAPI_PATH)
    return FileResponse(path, media_type="application/yaml")


@router.get("/docs/openapi.yaml", include_in_schema=False)
def serve_openapi_yaml_alias() -> FileResponse:
    return serve_openapi_yaml()
