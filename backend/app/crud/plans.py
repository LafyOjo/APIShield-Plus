from sqlalchemy.orm import Session

from app.models.plans import Plan


def get_plan_by_id(db: Session, plan_id: int) -> Plan | None:
    return db.query(Plan).filter(Plan.id == plan_id).first()


def get_plan_by_name(db: Session, name: str) -> Plan | None:
    return db.query(Plan).filter(Plan.name == name).first()


def list_active_plans(db: Session) -> list[Plan]:
    return db.query(Plan).filter(Plan.is_active.is_(True)).order_by(Plan.id).all()
