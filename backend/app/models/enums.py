from enum import Enum

# Stored as strings with DB check constraints (native enums disabled for easier evolution).


class RoleEnum(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    SECURITY_ADMIN = "security_admin"
    BILLING_ADMIN = "billing_admin"
    ANALYST = "analyst"
    VIEWER = "viewer"


class MembershipStatusEnum(str, Enum):
    ACTIVE = "active"
    INVITED = "invited"
    SUSPENDED = "suspended"


class WebsiteStatusEnum(str, Enum):
    # Paused websites should reject or ignore ingestion (enforced later).
    ACTIVE = "active"
    PAUSED = "paused"
    DELETED = "deleted"


class StatusIncidentStatusEnum(str, Enum):
    INVESTIGATING = "investigating"
    IDENTIFIED = "identified"
    MONITORING = "monitoring"
    RESOLVED = "resolved"


class StatusImpactEnum(str, Enum):
    MINOR = "minor"
    MAJOR = "major"
    CRITICAL = "critical"


class StatusComponentStatusEnum(str, Enum):
    OPERATIONAL = "operational"
    DEGRADED = "degraded"
    OUTAGE = "outage"
