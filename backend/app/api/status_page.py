from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.crud.status_page import ensure_status_components, list_public_incidents
from app.schemas.status_page import StatusComponentRead, StatusIncidentRead


router = APIRouter(prefix="/api/status", tags=["status"])


@router.get("/components", response_model=list[StatusComponentRead])
def list_components(db: Session = Depends(get_db)):
    return ensure_status_components(db)


@router.get("/incidents", response_model=list[StatusIncidentRead])
def list_incidents(db: Session = Depends(get_db)):
    return list_public_incidents(db)
