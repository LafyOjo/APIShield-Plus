from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_current_user
from app.core.db import get_db
from app.crud.marketplace import (
    create_template_submission,
    get_template,
    import_template,
    list_templates,
    serialize_template,
)
from app.schemas.marketplace import (
    MarketplaceImportRequest,
    MarketplaceImportResponse,
    MarketplaceTemplateCreate,
    MarketplaceTemplateRead,
)
from app.tenancy.dependencies import get_current_membership, require_role_in_tenant


router = APIRouter(tags=["marketplace"])
public_router = APIRouter(tags=["marketplace"])


@public_router.get("/public/marketplace", response_model=list[MarketplaceTemplateRead])
def list_public_templates(
    template_type: str | None = None,
    stack_type: str | None = None,
    search: str | None = None,
    tag: str | None = None,
    db=Depends(get_db),
):
    templates = list_templates(
        db,
        published_only=True,
        template_type=template_type,
        stack_type=stack_type,
        search=search,
        tags=[tag] if tag else None,
    )
    return [serialize_template(template) for template in templates]


@public_router.get("/public/marketplace/{template_id}", response_model=MarketplaceTemplateRead)
def get_public_template(
    template_id: int,
    db=Depends(get_db),
):
    template = get_template(db, template_id, published_only=True)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return serialize_template(template)


@router.get("/marketplace/templates", response_model=list[MarketplaceTemplateRead])
def list_marketplace_templates(
    template_type: str | None = None,
    stack_type: str | None = None,
    search: str | None = None,
    tag: str | None = None,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
    ctx=Depends(require_role_in_tenant(["viewer"], user_resolver=get_current_user)),
):
    get_current_membership(db, current_user, ctx.tenant_id)
    templates = list_templates(
        db,
        published_only=True,
        template_type=template_type,
        stack_type=stack_type,
        search=search,
        tags=[tag] if tag else None,
    )
    return [serialize_template(template) for template in templates]


@router.get("/marketplace/templates/{template_id}", response_model=MarketplaceTemplateRead)
def get_marketplace_template(
    template_id: int,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
    ctx=Depends(require_role_in_tenant(["viewer"], user_resolver=get_current_user)),
):
    get_current_membership(db, current_user, ctx.tenant_id)
    template = get_template(db, template_id, published_only=True)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return serialize_template(template)


@router.post("/marketplace/templates/submit", response_model=MarketplaceTemplateRead)
def submit_marketplace_template(
    payload: MarketplaceTemplateCreate,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
    ctx=Depends(require_role_in_tenant(["owner", "admin"], user_resolver=get_current_user)),
):
    get_current_membership(db, current_user, ctx.tenant_id)
    try:
        template = create_template_submission(
            db,
            template_type=payload.template_type,
            title=payload.title,
            description=payload.description,
            stack_type=payload.stack_type,
            tags=payload.tags,
            content_json=payload.content_json,
            author_user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return serialize_template(template)


@router.post("/marketplace/templates/{template_id}/import", response_model=MarketplaceImportResponse)
def import_marketplace_template(
    template_id: int,
    payload: MarketplaceImportRequest,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
    ctx=Depends(require_role_in_tenant(["owner", "admin"], user_resolver=get_current_user)),
):
    membership = get_current_membership(db, current_user, ctx.tenant_id)
    template = get_template(db, template_id, published_only=True)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    try:
        result = import_template(
            db,
            template=template,
            tenant_id=membership.tenant_id,
            incident_id=payload.incident_id,
            created_by_user_id=current_user.id,
        )
    except ValueError as exc:
        message = str(exc)
        status_code = status.HTTP_404_NOT_FOUND if "not found" in message.lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=message) from exc
    return result
