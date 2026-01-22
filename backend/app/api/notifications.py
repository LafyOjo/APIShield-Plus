from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.crypto import decrypt_json
from app.core.db import get_db
from app.core.entitlements import resolve_effective_entitlements
from app.entitlements.enforcement import assert_limit, require_feature
from app.crud.notification_channels import (
    create_channel,
    disable_channel,
    get_channel,
    list_channels,
    update_channel,
)
from app.crud.notification_rules import (
    create_rule,
    get_rule,
    list_rules,
    update_rule,
)
from app.crud.tenants import get_tenant_by_id, get_tenant_by_slug
from app.models.enums import RoleEnum
from app.models.notification_channels import NotificationChannel
from app.models.notification_deliveries import NotificationDelivery
from app.models.notification_rules import NotificationRuleChannel
from app.notifications.senders import get_sender
from app.schemas.notification_channels import (
    NotificationChannelCreate,
    NotificationChannelRead,
    NotificationChannelUpdate,
)
from app.schemas.notification_deliveries import NotificationDeliveryRead
from app.schemas.notification_rules import NotificationRuleCreate, NotificationRuleRead, NotificationRuleUpdate
from app.tenancy.dependencies import require_role_in_tenant


router = APIRouter(prefix="/notifications", tags=["notifications"])

ALLOWED_CHANNEL_TYPES = {"slack", "webhook", "email"}


def _resolve_tenant_id(db: Session, tenant_hint: str) -> int:
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


def _normalize_ts(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _enforce_channel_limit(db: Session, tenant_id: int, entitlements: dict) -> None:
    current = db.query(NotificationChannel).filter(NotificationChannel.tenant_id == tenant_id).count()
    assert_limit(
        entitlements,
        "notification_channels",
        current,
        mode="hard",
        message="Notification channel limit reached for plan",
    )


def _validate_channel_type(channel_type: str, entitlements: dict) -> str:
    normalized = (channel_type or "").strip().lower()
    if normalized not in ALLOWED_CHANNEL_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported channel type")
    if normalized == "webhook":
        require_feature(
            entitlements,
            "advanced_alerting",
            message="Webhook channels require advanced alerting",
        )
    return normalized


def _rule_read(db: Session, rule) -> NotificationRuleRead:
    channel_ids = [
        row.channel_id
        for row in db.query(NotificationRuleChannel.channel_id).filter(
            NotificationRuleChannel.rule_id == rule.id
        )
    ]
    return NotificationRuleRead(
        id=rule.id,
        name=rule.name,
        trigger_type=rule.trigger_type,
        is_enabled=rule.is_enabled,
        filters_json=rule.filters_json,
        thresholds_json=rule.thresholds_json,
        quiet_hours_json=rule.quiet_hours_json,
        route_to_channel_ids=channel_ids,
        created_by_user_id=rule.created_by_user_id,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


@router.get("/channels", response_model=list[NotificationChannelRead])
def list_notification_channels(
    db: Session = Depends(get_db),
    ctx=Depends(require_role_in_tenant([RoleEnum.VIEWER], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    return list_channels(db, tenant_id)


@router.post("/channels", response_model=NotificationChannelRead)
def create_notification_channel(
    payload: NotificationChannelCreate,
    db: Session = Depends(get_db),
    ctx=Depends(require_role_in_tenant([RoleEnum.ADMIN, RoleEnum.OWNER], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    entitlements = resolve_effective_entitlements(db, tenant_id)
    _enforce_channel_limit(db, tenant_id, entitlements)
    channel_type = _validate_channel_type(payload.type, entitlements)
    channel = create_channel(
        db,
        tenant_id=tenant_id,
        channel_type=channel_type,
        name=payload.name,
        created_by_user_id=ctx.user_id,
        is_enabled=payload.is_enabled if payload.is_enabled is not None else True,
        config_public=payload.config_public_json,
        config_secret=payload.config_secret,
        categories_allowed=payload.categories_allowed,
    )
    return channel


@router.patch("/channels/{channel_id}", response_model=NotificationChannelRead)
def update_notification_channel(
    channel_id: int,
    payload: NotificationChannelUpdate,
    db: Session = Depends(get_db),
    ctx=Depends(require_role_in_tenant([RoleEnum.ADMIN, RoleEnum.OWNER], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    channel = update_channel(
        db,
        tenant_id,
        channel_id,
        name=payload.name,
        is_enabled=payload.is_enabled,
        config_public=payload.config_public_json,
        config_secret=payload.config_secret,
        categories_allowed=payload.categories_allowed,
        last_tested_at=payload.last_tested_at,
        last_error=payload.last_error,
    )
    if not channel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")
    return channel


@router.delete("/channels/{channel_id}", response_model=NotificationChannelRead)
def delete_notification_channel(
    channel_id: int,
    db: Session = Depends(get_db),
    ctx=Depends(require_role_in_tenant([RoleEnum.ADMIN, RoleEnum.OWNER], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    channel = disable_channel(db, tenant_id, channel_id)
    if not channel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")
    return channel


@router.post("/channels/{channel_id}/test")
def test_notification_channel(
    channel_id: int,
    db: Session = Depends(get_db),
    ctx=Depends(require_role_in_tenant([RoleEnum.ADMIN, RoleEnum.OWNER], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    channel = get_channel(db, tenant_id, channel_id)
    if not channel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")
    sender = get_sender(channel.type)
    if not sender:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported channel type")

    config_public = channel.config_public_json or {}
    config_secret: dict = {}
    if channel.config_secret_enc:
        try:
            config_secret = decrypt_json(channel.config_secret_enc)
        except ValueError as exc:
            update_channel(
                db,
                tenant_id,
                channel_id,
                last_tested_at=datetime.now(timezone.utc).replace(tzinfo=None),
                last_error=str(exc),
            )
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if channel.type in {"slack", "webhook"} and not config_secret:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Channel secret not configured")

    payload = {
        "type": "test",
        "title": "Notification test",
        "message": "This is a test notification from APIShield+.",
    }
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        sender.send(
            channel=channel,
            payload=payload,
            event_type="notification_test",
            config_public=config_public,
            config_secret=config_secret,
        )
    except Exception as exc:
        update_channel(
            db,
            tenant_id,
            channel_id,
            last_tested_at=now,
            last_error=str(exc),
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    update_channel(
        db,
        tenant_id,
        channel_id,
        last_tested_at=now,
        last_error=None,
    )
    return {"ok": True}


@router.get("/rules", response_model=list[NotificationRuleRead])
def list_notification_rules(
    db: Session = Depends(get_db),
    ctx=Depends(require_role_in_tenant([RoleEnum.VIEWER], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    return [_rule_read(db, rule) for rule in list_rules(db, tenant_id)]


@router.post("/rules", response_model=NotificationRuleRead)
def create_notification_rule(
    payload: NotificationRuleCreate,
    db: Session = Depends(get_db),
    ctx=Depends(require_role_in_tenant([RoleEnum.ADMIN, RoleEnum.OWNER], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    try:
        rule = create_rule(
            db,
            tenant_id=tenant_id,
            name=payload.name,
            trigger_type=payload.trigger_type,
            created_by_user_id=ctx.user_id,
            is_enabled=payload.is_enabled if payload.is_enabled is not None else True,
            filters_json=payload.filters_json,
            thresholds_json=payload.thresholds_json,
            quiet_hours_json=payload.quiet_hours_json,
            route_to_channel_ids=payload.route_to_channel_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _rule_read(db, rule)


@router.patch("/rules/{rule_id}", response_model=NotificationRuleRead)
def update_notification_rule(
    rule_id: int,
    payload: NotificationRuleUpdate,
    db: Session = Depends(get_db),
    ctx=Depends(require_role_in_tenant([RoleEnum.ADMIN, RoleEnum.OWNER], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    try:
        rule = update_rule(
            db,
            tenant_id,
            rule_id,
            name=payload.name,
            trigger_type=payload.trigger_type,
            is_enabled=payload.is_enabled,
            filters_json=payload.filters_json,
            thresholds_json=payload.thresholds_json,
            quiet_hours_json=payload.quiet_hours_json,
            route_to_channel_ids=payload.route_to_channel_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    return _rule_read(db, rule)


@router.delete("/rules/{rule_id}", response_model=NotificationRuleRead)
def delete_notification_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    ctx=Depends(require_role_in_tenant([RoleEnum.ADMIN, RoleEnum.OWNER], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    rule = update_rule(db, tenant_id, rule_id, is_enabled=False)
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    return _rule_read(db, rule)


@router.get("/deliveries", response_model=list[NotificationDeliveryRead])
def list_notification_deliveries(
    status_value: str | None = Query(None, alias="status"),
    from_ts: datetime | None = Query(None, alias="from"),
    to_ts: datetime | None = Query(None, alias="to"),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    ctx=Depends(require_role_in_tenant([RoleEnum.VIEWER], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    query = db.query(NotificationDelivery).filter(NotificationDelivery.tenant_id == tenant_id)
    if status_value:
        query = query.filter(NotificationDelivery.status == status_value)
    from_ts = _normalize_ts(from_ts)
    to_ts = _normalize_ts(to_ts)
    if from_ts:
        query = query.filter(NotificationDelivery.created_at >= from_ts)
    if to_ts:
        query = query.filter(NotificationDelivery.created_at <= to_ts)
    rows = (
        query.order_by(NotificationDelivery.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return rows
