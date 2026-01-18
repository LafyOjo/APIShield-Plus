"""
Lightweight request-scoped context for tenancy-aware operations.
"""

from dataclasses import dataclass
from typing import Optional

from app.models.enums import RoleEnum

@dataclass
class RequestContext:
    """
    Captures the caller's tenant context and role for downstream checks.
    """

    request_id: str
    tenant_id: Optional[str]
    user_id: Optional[int]
    username: Optional[str]
    role: Optional[RoleEnum]
