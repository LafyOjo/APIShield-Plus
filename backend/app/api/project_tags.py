from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_current_user
from app.core.db import get_db
from app.crud.project_tags import (
    attach_tag_to_website,
    create_tag,
    delete_tag,
    detach_tag_from_website,
    list_tags,
)
from app.crud.tenants import get_tenant_by_id, get_tenant_by_slug
from app.models.enums import RoleEnum
from app.schemas.project_tags import ProjectTagCreate, ProjectTagRead
from app.tenancy.dependencies import require_roles, require_tenant_context


router = APIRouter(tags=["tags"])


def _resolve_tenant_id(db, tenant_hint: str) -> int:
    if not tenant_hint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    tenant_value = tenant_hint.strip()
    tenant = (
        get_tenant_by_id(db, int(tenant_value))
        if tenant_value.isdigit()
        else get_tenant_by_slug(db, tenant_value)
    )
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant.id


@router.get("/tags", response_model=list[ProjectTagRead])
def list_tags_endpoint(
    db=Depends(get_db),
    ctx=Depends(require_tenant_context(user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    return list_tags(db, tenant_id)


@router.post("/tags", response_model=ProjectTagRead)
def create_tag_endpoint(
    payload: ProjectTagCreate,
    db=Depends(get_db),
    ctx=Depends(require_roles([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    try:
        return create_tag(db, tenant_id, payload.name, payload.color)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/websites/{website_id}/tags/{tag_id}")
def attach_tag_endpoint(
    website_id: int,
    tag_id: int,
    db=Depends(get_db),
    ctx=Depends(require_roles([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    try:
        attach_tag_to_website(db, tenant_id, website_id, tag_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"status": "attached"}


@router.delete("/websites/{website_id}/tags/{tag_id}")
def detach_tag_endpoint(
    website_id: int,
    tag_id: int,
    db=Depends(get_db),
    ctx=Depends(require_roles([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    success = detach_tag_from_website(db, tenant_id, website_id, tag_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag assignment not found")
    return {"status": "detached"}
