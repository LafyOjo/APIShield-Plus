from sqlalchemy.orm import Session

from app.core.entitlements import validate_entitlement_source, validate_feature
from app.models.feature_entitlements import FeatureEntitlement
from app.models.plans import Plan


def get_entitlements(db: Session, tenant_id: int) -> list[FeatureEntitlement]:
    return (
        db.query(FeatureEntitlement)
        .filter(FeatureEntitlement.tenant_id == tenant_id)
        .order_by(FeatureEntitlement.feature)
        .all()
    )


def upsert_entitlement(
    db: Session,
    tenant_id: int,
    feature: str,
    enabled: bool,
    source: str,
    source_plan_id: int | None = None,
    updated_by_user_id: int | None = None,
) -> FeatureEntitlement:
    validate_feature(feature)
    validate_entitlement_source(source)
    if source_plan_id is not None and source not in {"plan", "promotion", "trial"}:
        raise ValueError("source_plan_id is only valid for plan-based sources")
    entitlement = (
        db.query(FeatureEntitlement)
        .filter(
            FeatureEntitlement.tenant_id == tenant_id,
            FeatureEntitlement.feature == feature,
        )
        .first()
    )
    if entitlement:
        entitlement.enabled = enabled
        entitlement.source = source
        entitlement.source_plan_id = source_plan_id
        entitlement.updated_by_user_id = updated_by_user_id
    else:
        entitlement = FeatureEntitlement(
            tenant_id=tenant_id,
            feature=feature,
            enabled=enabled,
            source=source,
            source_plan_id=source_plan_id,
            updated_by_user_id=updated_by_user_id,
        )
        db.add(entitlement)
    db.commit()
    db.refresh(entitlement)
    from app.core.entitlements import invalidate_entitlement_cache

    invalidate_entitlement_cache(tenant_id)
    return entitlement


def seed_entitlements_from_plan(
    db: Session,
    tenant_id: int,
    plan: Plan | None,
) -> list[FeatureEntitlement]:
    if plan is None:
        return []
    features = plan.features_json or {}
    seeded: list[FeatureEntitlement] = []
    for feature, enabled in features.items():
        try:
            validate_feature(feature)
        except ValueError:
            continue
        existing = (
            db.query(FeatureEntitlement)
            .filter(
                FeatureEntitlement.tenant_id == tenant_id,
                FeatureEntitlement.feature == feature,
            )
            .first()
        )
        if existing and existing.source != "plan":
            continue
        seeded.append(
            upsert_entitlement(
                db,
                tenant_id=tenant_id,
                feature=feature,
                enabled=bool(enabled),
                source="plan",
                source_plan_id=plan.id,
            )
        )
    return seeded
