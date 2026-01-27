from __future__ import annotations

from xml.etree import ElementTree as ET

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.crud.tenant_sso import get_sso_config
from app.crud.tenants import get_tenant_by_id, get_tenant_by_slug
from app.entitlements.enforcement import require_feature
from app.entitlements.resolver import resolve_entitlements_for_tenant


SAML_METADATA_NS = "urn:oasis:names:tc:SAML:2.0:metadata"
DS_NS = "http://www.w3.org/2000/09/xmldsig#"

ET.register_namespace("", SAML_METADATA_NS)
ET.register_namespace("ds", DS_NS)

router = APIRouter(prefix="/auth/saml", tags=["sso"])


def _resolve_tenant(db: Session, tenant_hint: str | None):
    if not tenant_hint:
        return None
    tenant_value = tenant_hint.strip()
    tenant = (
        get_tenant_by_id(db, int(tenant_value))
        if tenant_value.isdigit()
        else get_tenant_by_slug(db, tenant_value)
    )
    return tenant


def _normalize_cert(cert: str | None) -> str | None:
    if not cert:
        return None
    lines = [
        line.strip()
        for line in cert.strip().splitlines()
        if line.strip()
    ]
    filtered = [
        line
        for line in lines
        if "BEGIN CERTIFICATE" not in line and "END CERTIFICATE" not in line
    ]
    return "".join(filtered) if filtered else None


def _build_metadata_xml(sp_entity_id: str, acs_url: str, sp_x509_cert: str | None) -> bytes:
    entity_descriptor = ET.Element(
        f"{{{SAML_METADATA_NS}}}EntityDescriptor",
        {"entityID": sp_entity_id},
    )
    sp_descriptor = ET.SubElement(
        entity_descriptor,
        f"{{{SAML_METADATA_NS}}}SPSSODescriptor",
        {
            "protocolSupportEnumeration": "urn:oasis:names:tc:SAML:2.0:protocol",
        },
    )

    cert_body = _normalize_cert(sp_x509_cert)
    if cert_body:
        key_descriptor = ET.SubElement(
            sp_descriptor,
            f"{{{SAML_METADATA_NS}}}KeyDescriptor",
            {"use": "signing"},
        )
        key_info = ET.SubElement(key_descriptor, f"{{{DS_NS}}}KeyInfo")
        x509_data = ET.SubElement(key_info, f"{{{DS_NS}}}X509Data")
        ET.SubElement(x509_data, f"{{{DS_NS}}}X509Certificate").text = cert_body

    ET.SubElement(
        sp_descriptor,
        f"{{{SAML_METADATA_NS}}}AssertionConsumerService",
        {
            "Binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
            "Location": acs_url,
            "index": "0",
            "isDefault": "true",
        },
    )

    return ET.tostring(entity_descriptor, encoding="utf-8", xml_declaration=True)


@router.get("/metadata")
def saml_metadata(
    tenant_id: str | None = None,
    db: Session = Depends(get_db),
):
    tenant = _resolve_tenant(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    entitlements = resolve_entitlements_for_tenant(db, tenant.id)
    require_feature(entitlements, "sso_saml", message="SAML SSO requires an Enterprise plan")
    config = get_sso_config(db, tenant.id)
    if not config or not config.is_enabled or config.provider != "saml":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="SAML not enabled")
    if not config.sp_entity_id or not config.sp_acs_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="SAML configuration incomplete")

    xml_bytes = _build_metadata_xml(
        sp_entity_id=config.sp_entity_id,
        acs_url=config.sp_acs_url,
        sp_x509_cert=config.sp_x509_cert,
    )
    return Response(content=xml_bytes, media_type="application/samlmetadata+xml")


@router.post("/acs")
async def saml_acs(_request: Request):
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="SAML ACS not implemented",
    )
