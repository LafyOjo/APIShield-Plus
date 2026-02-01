from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import require_platform_admin
from app.core.db import get_db
from app.crud.marketplace import list_templates, get_template, update_template, serialize_template
from app.schemas.marketplace import MarketplaceTemplateRead, MarketplaceTemplateUpdate


router = APIRouter(prefix="/admin/marketplace", tags=["marketplace-admin"])


@router.get("/templates", response_model=list[MarketplaceTemplateRead])
def list_admin_templates(
    template_type: str | None = None,
    status_filter: str | None = None,
    source: str | None = None,
    db=Depends(get_db),
    _current_user=Depends(require_platform_admin()),
):
    templates = list_templates(
        db,
        published_only=False if status_filter is None else status_filter.lower() == "published",
        template_type=template_type,
        source=source,
    )
    if status_filter:
        templates = [item for item in templates if item.status == status_filter.lower()]
    return [serialize_template(template) for template in templates]


@router.get("/templates/{template_id}", response_model=MarketplaceTemplateRead)
def get_admin_template(
    template_id: int,
    db=Depends(get_db),
    _current_user=Depends(require_platform_admin()),
):
    template = get_template(db, template_id, published_only=False)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return serialize_template(template)


@router.patch("/templates/{template_id}", response_model=MarketplaceTemplateRead)
def update_admin_template(
    template_id: int,
    payload: MarketplaceTemplateUpdate,
    db=Depends(get_db),
    _current_user=Depends(require_platform_admin()),
):
    try:
        template = update_template(
            db,
            template_id,
            title=payload.title,
            description=payload.description,
            stack_type=payload.stack_type,
            tags=payload.tags,
            content_json=payload.content_json,
            status=payload.status,
            source=payload.source,
            safety_notes=payload.safety_notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return serialize_template(template)
