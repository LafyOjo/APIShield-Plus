"""
Custom exceptions for tenant resolution and authorization.
"""


class TenantNotSelected(Exception):
    """Raised when a tenant context is required but none was provided."""


class TenantForbidden(Exception):
    """Raised when a user attempts an action outside their tenant or role."""


class TenantNotFound(Exception):
    """Raised when a tenant or resource for that tenant does not exist."""
