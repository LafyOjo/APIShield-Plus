from enum import Enum

# Stored as strings with DB check constraints (native enums disabled for easier evolution).


class RoleEnum(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
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
