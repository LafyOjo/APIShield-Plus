"""add geo-ready fields to event, alert, and audit logs

Revision ID: fd2e3f4a5b6c
Revises: fc1d2e3f4a5b
Create Date: 2026-01-18 12:30:00.000000
"""
from typing import Sequence, Union

import hashlib
import hmac
import os
from ipaddress import ip_address

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "fd2e3f4a5b6c"
down_revision: Union[str, None] = "fc1d2e3f4a5b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _normalize_ip(value: str) -> str | None:
    if not value:
        return None
    try:
        return str(ip_address(value.strip()))
    except ValueError:
        return None


def _hash_ip(secret: str, tenant_id: int, ip_value: str) -> str | None:
    normalized = _normalize_ip(ip_value)
    if not normalized:
        return None
    secret_bytes = secret.encode("utf-8")
    message = f"tenant:{tenant_id}".encode("utf-8")
    salt = hmac.new(secret_bytes, message, hashlib.sha256).digest()
    return hmac.new(salt, normalized.encode("utf-8"), hashlib.sha256).hexdigest()


def _backfill_ip_hash(conn, table_name: str) -> None:
    secret = os.getenv("SECRET_KEY")
    if not secret:
        return
    rows = conn.execute(
        sa.text(
            f"SELECT id, tenant_id, client_ip FROM {table_name} "
            "WHERE tenant_id IS NOT NULL AND client_ip IS NOT NULL AND ip_hash IS NULL"
        )
    ).fetchall()
    for row in rows:
        hashed = _hash_ip(secret, int(row.tenant_id), row.client_ip)
        if not hashed:
            continue
        conn.execute(
            sa.text(f"UPDATE {table_name} SET ip_hash = :ip_hash WHERE id = :id"),
            {"ip_hash": hashed, "id": row.id},
        )


def upgrade() -> None:
    with op.batch_alter_table("events") as batch_op:
        batch_op.add_column(sa.Column("client_ip", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("ip_hash", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("user_agent", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("request_path", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("referrer", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("country_code", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("region", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("city", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("latitude", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("longitude", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("asn", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("is_datacenter", sa.Boolean(), nullable=True))
        batch_op.create_index(
            "ix_events_tenant_ip_hash_time",
            ["tenant_id", "ip_hash", "timestamp"],
        )

    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.add_column(sa.Column("client_ip", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("ip_hash", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("user_agent", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("request_path", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("referrer", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("country_code", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("region", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("city", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("latitude", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("longitude", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("asn", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("is_datacenter", sa.Boolean(), nullable=True))
        batch_op.create_index(
            "ix_audit_tenant_ip_hash_time",
            ["tenant_id", "ip_hash", "timestamp"],
        )

    with op.batch_alter_table("alerts") as batch_op:
        batch_op.add_column(sa.Column("client_ip", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("user_agent", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("request_path", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("referrer", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("country_code", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("region", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("city", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("latitude", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("longitude", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("asn", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("is_datacenter", sa.Boolean(), nullable=True))
        batch_op.drop_index("ix_alerts_tenant_ip_hash")
        batch_op.create_index(
            "ix_alerts_tenant_ip_hash_time",
            ["tenant_id", "ip_hash", "timestamp"],
        )

    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE alerts SET client_ip = ip_address "
            "WHERE client_ip IS NULL AND ip_address IS NOT NULL"
        )
    )
    _backfill_ip_hash(conn, "alerts")
    _backfill_ip_hash(conn, "events")
    _backfill_ip_hash(conn, "audit_logs")


def downgrade() -> None:
    with op.batch_alter_table("alerts") as batch_op:
        batch_op.drop_index("ix_alerts_tenant_ip_hash_time")
        batch_op.create_index("ix_alerts_tenant_ip_hash", ["tenant_id", "ip_hash"])
        batch_op.drop_column("is_datacenter")
        batch_op.drop_column("asn")
        batch_op.drop_column("longitude")
        batch_op.drop_column("latitude")
        batch_op.drop_column("city")
        batch_op.drop_column("region")
        batch_op.drop_column("country_code")
        batch_op.drop_column("referrer")
        batch_op.drop_column("request_path")
        batch_op.drop_column("user_agent")
        batch_op.drop_column("client_ip")

    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.drop_index("ix_audit_tenant_ip_hash_time")
        batch_op.drop_column("is_datacenter")
        batch_op.drop_column("asn")
        batch_op.drop_column("longitude")
        batch_op.drop_column("latitude")
        batch_op.drop_column("city")
        batch_op.drop_column("region")
        batch_op.drop_column("country_code")
        batch_op.drop_column("referrer")
        batch_op.drop_column("request_path")
        batch_op.drop_column("user_agent")
        batch_op.drop_column("ip_hash")
        batch_op.drop_column("client_ip")

    with op.batch_alter_table("events") as batch_op:
        batch_op.drop_index("ix_events_tenant_ip_hash_time")
        batch_op.drop_column("is_datacenter")
        batch_op.drop_column("asn")
        batch_op.drop_column("longitude")
        batch_op.drop_column("latitude")
        batch_op.drop_column("city")
        batch_op.drop_column("region")
        batch_op.drop_column("country_code")
        batch_op.drop_column("referrer")
        batch_op.drop_column("request_path")
        batch_op.drop_column("user_agent")
        batch_op.drop_column("ip_hash")
        batch_op.drop_column("client_ip")
