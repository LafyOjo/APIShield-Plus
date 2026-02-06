from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import func

from app.core.config import settings
from app.core.db import get_db
from app.core.rate_limit import allow, is_banned, register_abuse_attempt, register_invalid_attempt
from app.core.score_signing import load_private_key, sign_payload
from app.models.trust_scoring import TrustSnapshot
from app.models.websites import Website
from app.models.enums import WebsiteStatusEnum


router = APIRouter(tags=["public-score"])


def _cache_headers(response: JSONResponse) -> None:
    response.headers["Cache-Control"] = f"public, max-age={settings.TRUST_SCORE_CACHE_SECONDS}"
    response.headers["Access-Control-Allow-Origin"] = "*"


def _etag_for_payload(payload: str) -> str:
    digest = sha256(payload.encode("utf-8")).hexdigest()
    return f"\"{digest}\""


def _latest_snapshot(db, website_id: int) -> TrustSnapshot | None:
    return (
        db.query(TrustSnapshot)
        .filter(
            TrustSnapshot.website_id == website_id,
            TrustSnapshot.path.is_(None),
            TrustSnapshot.is_demo.is_(False),
        )
        .order_by(TrustSnapshot.bucket_start.desc())
        .first()
    )


def _compute_verified(score: int | None, confidence: float | None) -> bool:
    if score is None or confidence is None:
        return False
    return score >= 80 and confidence >= 0.6


def _score_summary(db, website_id: int, *, hours: int = 24) -> dict[str, Any] | None:
    window_start = datetime.utcnow() - timedelta(hours=hours)
    row = (
        db.query(
            func.count(TrustSnapshot.id),
            func.avg(TrustSnapshot.trust_score),
            func.min(TrustSnapshot.trust_score),
            func.max(TrustSnapshot.trust_score),
        )
        .filter(
            TrustSnapshot.website_id == website_id,
            TrustSnapshot.path.is_(None),
            TrustSnapshot.is_demo.is_(False),
            TrustSnapshot.bucket_start >= window_start,
        )
        .first()
    )
    if not row or not row[0]:
        return None
    return {
        "window_hours": hours,
        "count": int(row[0]),
        "avg": float(row[1]) if row[1] is not None else None,
        "min": int(row[2]) if row[2] is not None else None,
        "max": int(row[3]) if row[3] is not None else None,
    }


def _client_subject(request: Request) -> str | None:
    return getattr(request.state, "client_ip", None) or (request.client.host if request.client else None)


@router.get("/public/score/keys")
def get_score_public_key():
    if not settings.TRUST_SCORE_SIGNING_PUBLIC_KEY or not settings.TRUST_SCORE_SIGNING_KEY_ID:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Public key not configured")
    return {
        "proof_key_id": settings.TRUST_SCORE_SIGNING_KEY_ID,
        "public_key": settings.TRUST_SCORE_SIGNING_PUBLIC_KEY,
        "algorithm": "ed25519",
    }


@router.get("/public/score/v1")
def get_public_score(
    website_id: int,
    request: Request,
    db=Depends(get_db),
):
    subject = _client_subject(request)
    banned, retry_after = is_banned(subject)
    if banned:
        response = JSONResponse(
            {"detail": "Too many requests"}, status_code=status.HTTP_429_TOO_MANY_REQUESTS
        )
        response.headers["Retry-After"] = str(retry_after)
        return response

    rpm = settings.TRUST_SCORE_RPM
    burst = settings.TRUST_SCORE_BURST
    allowed, wait_seconds = allow(
        f"public_score:{subject}",
        capacity=burst,
        refill_rate_per_sec=max(1, rpm) / 60,
    )
    if not allowed:
        register_abuse_attempt(
            subject,
            threshold=settings.TRUST_SCORE_ABUSE_THRESHOLD,
            ban_seconds=settings.TRUST_SCORE_BAN_SECONDS,
        )
        response = JSONResponse(
            {"detail": "Rate limit exceeded"}, status_code=status.HTTP_429_TOO_MANY_REQUESTS
        )
        response.headers["Retry-After"] = str(wait_seconds)
        return response

    website = (
        db.query(Website)
        .filter(Website.id == website_id)
        .first()
    )
    if not website or website.deleted_at is not None or website.status == WebsiteStatusEnum.DELETED:
        register_invalid_attempt(
            subject,
            threshold=settings.TRUST_SCORE_ABUSE_THRESHOLD,
            ban_seconds=settings.TRUST_SCORE_BAN_SECONDS,
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Website not found")

    snapshot = _latest_snapshot(db, website_id)
    trust_score = snapshot.trust_score if snapshot else None
    confidence = snapshot.confidence if snapshot else None
    last_updated = snapshot.bucket_start if snapshot else None

    payload: dict[str, Any] = {
        "website_id": website_id,
        "trust_score_current": trust_score,
        "verified_status": _compute_verified(trust_score, confidence),
        "last_updated_at": last_updated.isoformat() if isinstance(last_updated, datetime) else None,
        "transparency_level": "summary",
        "score_history_summary": _score_summary(db, website_id),
        "proof_key_id": settings.TRUST_SCORE_SIGNING_KEY_ID,
    }

    if not settings.TRUST_SCORE_SIGNING_PRIVATE_KEY or not settings.TRUST_SCORE_SIGNING_KEY_ID:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Signing key not configured")
    try:
        private_key = load_private_key(settings.TRUST_SCORE_SIGNING_PRIVATE_KEY)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Signing key invalid") from exc

    signature = sign_payload(payload, private_key)
    payload_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=False, default=str)
    response = JSONResponse(payload)
    response.headers["X-Proof-Signature"] = signature
    response.headers["X-Proof-Key-Id"] = settings.TRUST_SCORE_SIGNING_KEY_ID or ""
    _cache_headers(response)
    response.headers["ETag"] = _etag_for_payload(payload_json)
    return response
