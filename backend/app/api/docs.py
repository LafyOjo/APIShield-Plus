from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_current_user
from app.schemas.docs import DocDetail, DocMeta


router = APIRouter(prefix="/docs", tags=["docs"])

DOCS_DIR = Path(__file__).resolve().parents[1] / "docs_content"
MANIFEST_PATH = DOCS_DIR / "index.json"


def _extract_headings(markdown: str) -> list[str]:
    headings: list[str] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue
        title = stripped.lstrip("#").strip()
        if title:
            headings.append(title)
    return headings


@lru_cache(maxsize=1)
def _load_manifest() -> list[dict]:
    if not MANIFEST_PATH.exists():
        raise RuntimeError("Docs manifest not found")
    with MANIFEST_PATH.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise RuntimeError("Docs manifest must be a list")
    return data


def _get_doc_meta(slug: str) -> dict | None:
    for entry in _load_manifest():
        if entry.get("slug") == slug:
            return entry
    return None


def _load_doc_content(slug: str) -> str:
    meta = _get_doc_meta(slug)
    if not meta:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doc not found")
    filename = meta.get("file")
    if not filename:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doc not found")
    path = (DOCS_DIR / filename).resolve()
    if DOCS_DIR not in path.parents:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid doc path")
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doc not found")
    return path.read_text(encoding="utf-8")


@router.get("", response_model=list[DocMeta])
def list_docs(_user=Depends(get_current_user)) -> list[DocMeta]:
    docs: list[DocMeta] = []
    for entry in _load_manifest():
        slug = entry.get("slug")
        if not slug:
            continue
        content = _load_doc_content(slug)
        docs.append(
            DocMeta(
                slug=slug,
                title=entry.get("title", slug),
                section=entry.get("section", "General"),
                summary=entry.get("summary"),
                headings=_extract_headings(content),
            )
        )
    return docs


@router.get("/{slug}", response_model=DocDetail)
def get_doc(slug: str, _user=Depends(get_current_user)) -> DocDetail:
    meta = _get_doc_meta(slug)
    if not meta:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doc not found")
    content = _load_doc_content(slug)
    return DocDetail(
        slug=slug,
        title=meta.get("title", slug),
        section=meta.get("section", "General"),
        summary=meta.get("summary"),
        headings=_extract_headings(content),
        content=content,
    )
