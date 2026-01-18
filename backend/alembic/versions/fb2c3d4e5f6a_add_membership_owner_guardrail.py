"""add membership owner invariant trigger (postgres only)

Revision ID: fb2c3d4e5f6a
Revises: fa1b2c3d4e5f
Create Date: 2026-01-16 21:10:00.000000
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "fb2c3d4e5f6a"
down_revision: Union[str, None] = "fa1b2c3d4e5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return
    op.execute(
        """
        CREATE OR REPLACE FUNCTION enforce_membership_owner_invariant()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'UPDATE' THEN
                IF OLD.role = 'owner'
                    AND OLD.status = 'active'
                    AND (NEW.role <> 'owner' OR NEW.status <> 'active') THEN
                    IF (
                        SELECT COUNT(*) FROM memberships
                        WHERE tenant_id = OLD.tenant_id
                          AND role = 'owner'
                          AND status = 'active'
                          AND id <> OLD.id
                    ) = 0 THEN
                        RAISE EXCEPTION 'Cannot remove last owner for tenant %', OLD.tenant_id;
                    END IF;
                END IF;
                RETURN NEW;
            ELSIF TG_OP = 'DELETE' THEN
                IF OLD.role = 'owner' AND OLD.status = 'active' THEN
                    IF (
                        SELECT COUNT(*) FROM memberships
                        WHERE tenant_id = OLD.tenant_id
                          AND role = 'owner'
                          AND status = 'active'
                          AND id <> OLD.id
                    ) = 0 THEN
                        RAISE EXCEPTION 'Cannot remove last owner for tenant %', OLD.tenant_id;
                    END IF;
                END IF;
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_memberships_owner_invariant
        BEFORE UPDATE OR DELETE ON memberships
        FOR EACH ROW
        EXECUTE FUNCTION enforce_membership_owner_invariant();
        """
    )


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return
    op.execute(
        "DROP TRIGGER IF EXISTS trg_memberships_owner_invariant ON memberships;"
    )
    op.execute("DROP FUNCTION IF EXISTS enforce_membership_owner_invariant();")
