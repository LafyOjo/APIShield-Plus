from __future__ import annotations

import time
from datetime import datetime
from hashlib import sha256
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, PlainTextResponse

from app.core.badges import (
    apply_badge_policy_to_payload,
    extract_badge_key,
    sign_badge_request,
    verify_badge_signature,
)
from app.core.branding import format_badge_brand_label, resolve_effective_badge_branding_mode
from app.core.config import settings
from app.core.db import get_db
from app.crud.tenant_branding import get_branding
from app.entitlements.resolver import resolve_entitlements_for_tenant
from app.models.enums import WebsiteStatusEnum
from app.models.trust_badges import TrustBadgeConfig
from app.models.trust_scoring import TrustSnapshot
from app.models.websites import Website


router = APIRouter(tags=["public-badge"])


def _base_url(request: Request) -> str:
    return (settings.APP_BASE_URL or str(request.base_url)).rstrip("/")


def _badge_cache_headers(response, *, max_age: int) -> None:
    response.headers["Cache-Control"] = f"public, max-age={max_age}"
    response.headers["Access-Control-Allow-Origin"] = "*"


def _etag_for_payload(payload: str) -> str:
    digest = sha256(payload.encode("utf-8")).hexdigest()
    return f"\"{digest}\""


def _load_enabled_badge(db, website_id: int) -> tuple[TrustBadgeConfig, Website]:
    config = (
        db.query(TrustBadgeConfig)
        .filter(TrustBadgeConfig.website_id == website_id)
        .first()
    )
    if not config or not config.is_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Badge not enabled")

    website = (
        db.query(Website)
        .filter(Website.id == website_id)
        .first()
    )
    if not website or website.tenant_id != config.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Website not found")
    if website.deleted_at is not None or website.status == WebsiteStatusEnum.DELETED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Website not found")
    return config, website


def _latest_snapshot(db, tenant_id: int, website_id: int) -> TrustSnapshot | None:
    return (
        db.query(TrustSnapshot)
        .filter(
            TrustSnapshot.tenant_id == tenant_id,
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


def _render_badge_js(data_url: str) -> str:
    return f"""(function(){{
  var dataUrl = \"{data_url}\";
  function safeText(value){{
    return value == null ? \"\" : String(value);
  }}
  function formatUpdated(value){{
    if (!value) return \"\";
    try {{
      var date = new Date(value);
      if (isNaN(date.getTime())) return \"\";
      return date.toLocaleString();
    }} catch (err) {{
      return \"\";
    }}
  }}
  function render(container, data){{
    var style = (data.style || \"light\").toLowerCase();
    var palette = {{
      light: {{
        bg: \"#ffffff\",
        text: \"#1f2933\",
        border: \"#d9e2ec\",
        accent: \"#2563eb\"
      }},
      dark: {{
        bg: \"#111827\",
        text: \"#f9fafb\",
        border: \"#374151\",
        accent: \"#38bdf8\"
      }},
      minimal: {{
        bg: \"#f8fafc\",
        text: \"#1e293b\",
        border: \"#e2e8f0\",
        accent: \"#0f172a\"
      }}
    }};
    var colors = palette[style] || palette.light;
    var badge = document.createElement(data.clickthrough_url ? \"a\" : \"div\");
    if (data.clickthrough_url) {{
      badge.href = data.clickthrough_url;
      badge.target = \"_blank\";
      badge.rel = \"noopener noreferrer\";
    }}
    badge.style.cssText = [
      \"display:inline-flex\",
      \"align-items:center\",
      \"gap:8px\",
      \"padding:8px 12px\",
      \"border-radius:12px\",
      \"border:1px solid \" + colors.border,
      \"background:\" + colors.bg,
      \"color:\" + colors.text,
      \"font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial\",
      \"font-size:12px\",
      \"line-height:1.2\",
      \"text-decoration:none\"
    ].join(\";\");

    var scoreValue = data.trust_score;
    var scoreText = scoreValue == null ? \"Collecting data\" : (\"TrustScore \" + scoreValue + \"/100\");
    if (!data.show_score && scoreValue != null) {{
      scoreText = \"TrustScore verified\";
    }}
    var scoreEl = document.createElement(\"div\");
    scoreEl.textContent = scoreText;
    scoreEl.style.fontWeight = \"600\";
    scoreEl.style.color = colors.accent;

    var metaEl = document.createElement(\"div\");
    metaEl.style.display = \"flex\";
    metaEl.style.flexDirection = \"column\";
    metaEl.style.gap = \"2px\";

    var updated = formatUpdated(data.updated_at);
    if (updated) {{
      var updatedEl = document.createElement(\"div\");
      updatedEl.textContent = \"Updated \" + updated;
      updatedEl.style.fontSize = \"10px\";
      updatedEl.style.opacity = \"0.7\";
      metaEl.appendChild(updatedEl);
    }}

    badge.appendChild(scoreEl);
    badge.appendChild(metaEl);

    if (data.show_branding) {{
      var brandEl = document.createElement(\"div\");
      brandEl.textContent = safeText(data.brand_label || \"Security monitored\");
      brandEl.style.fontSize = \"10px\";
      brandEl.style.opacity = \"0.65\";
      badge.appendChild(brandEl);
    }}

    container.innerHTML = \"\";
    container.appendChild(badge);
  }}

  function init(){{
    var script = document.currentScript || document.querySelector('script[src*="/public/badge.js"]');
    if (!script || !script.parentNode) return;
    var container = document.createElement(\"div\");
    container.setAttribute(\"data-apishield-badge\", \"true\");
    script.parentNode.insertBefore(container, script);
    fetch(dataUrl, {{mode: \"cors\"}})
      .then(function(resp){{ return resp.json(); }})
      .then(function(data){{ render(container, data); }})
      .catch(function(){{}});
  }}

  if (document.readyState === \"loading\") {{
    document.addEventListener(\"DOMContentLoaded\", init);
  }} else {{
    init();
  }}
}})();"""


@router.get("/public/badge.js", include_in_schema=False)
def serve_badge_js(
    website_id: int,
    request: Request,
    db=Depends(get_db),
):
    config, _website = _load_enabled_badge(db, website_id)
    key = extract_badge_key(config)
    ts = int(time.time())
    sig = sign_badge_request(website_id, ts, key)
    data_url = f"{_base_url(request)}/public/badge/data?website_id={website_id}&ts={ts}&sig={sig}"
    js = _render_badge_js(data_url)
    response = PlainTextResponse(js, media_type="application/javascript")
    _badge_cache_headers(response, max_age=settings.BADGE_JS_CACHE_SECONDS)
    response.headers["ETag"] = _etag_for_payload(js)
    return response


@router.get("/public/badge/data", include_in_schema=False)
def serve_badge_data(
    website_id: int,
    ts: int,
    sig: str,
    request: Request,
    db=Depends(get_db),
):
    config, website = _load_enabled_badge(db, website_id)
    try:
        key = extract_badge_key(config)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Badge unavailable") from exc

    if not verify_badge_signature(
        website_id,
        ts,
        sig,
        key,
        ttl_seconds=settings.BADGE_SIGNATURE_TTL_SECONDS,
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid badge signature")

    entitlements = resolve_entitlements_for_tenant(db, website.tenant_id)
    branding = get_branding(db, website.tenant_id)
    snapshot = _latest_snapshot(db, website.tenant_id, website_id)

    trust_score = snapshot.trust_score if snapshot else None
    confidence = snapshot.confidence if snapshot else None
    updated_at = snapshot.bucket_start if snapshot else None
    status_label = "ok" if snapshot else "collecting"

    branding_mode = resolve_effective_badge_branding_mode(
        branding.badge_branding_mode if branding else None,
        entitlements.get("plan_key"),
    )
    brand_label = format_badge_brand_label(
        branding_mode,
        branding.brand_name if branding else None,
    )

    payload: dict[str, Any] = {
        "website_id": website_id,
        "trust_score": trust_score,
        "confidence": confidence,
        "updated_at": updated_at.isoformat() if isinstance(updated_at, datetime) else None,
        "status": status_label,
        "style": config.style,
        "show_score": config.show_score,
        "show_branding": config.show_branding,
        "clickthrough_url": config.clickthrough_url,
        "verified": _compute_verified(trust_score, confidence),
        "brand_label": brand_label,
    }
    payload = apply_badge_policy_to_payload(
        payload,
        entitlements.get("plan_key"),
        branding_mode=branding_mode,
    )

    payload_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=False, default=str)
    response = JSONResponse(payload)
    _badge_cache_headers(response, max_age=settings.BADGE_DATA_CACHE_SECONDS)
    response.headers["ETag"] = _etag_for_payload(payload_json)
    return response
