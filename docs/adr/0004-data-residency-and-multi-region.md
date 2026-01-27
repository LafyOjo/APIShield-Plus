# ADR 0004: Data Residency & Multi-Region Readiness

Status: Accepted  
Date: 2026-01-24

## Context
Enterprise customers require data residency (EU/US) and an architecture that can
evolve into true multi-region without a rewrite. We are not implementing full
multi-region routing now, but we need the data model and configuration to avoid
lock-in to a single region.

## Decision
We will:
- Store a **data region** on each tenant (default `us`) and track the
  **created_region** separately.
- Introduce region-aware configuration maps for future routing:
  - `REGION_DB_URLS` (region → database URL)
  - `REGION_EXPORT_TARGETS` (region → export target)
- Update export paths to include a `region=<region>` prefix.

## Data Model
`Tenant` now includes:
- `data_region`: `"us"` or `"eu"` (default `us`)
- `created_region`: region at creation time
- `allowed_regions`: optional list of allowed residency regions

## Operational Notes
- **Routing** (future): API requests will resolve the active tenant and route to
  the correct region’s DB and storage layer.
- **Tenant moves** (future): moving a tenant across regions requires data copy,
  dual-write or read-only windows, and careful DNS/hosted routing changes.
- **Exports** now include region prefix to prevent cross-region mix-ups.

## Consequences
- Single-region deployments continue to work with `DEFAULT_TENANT_REGION=us`.
- Region-aware exports are ready for multi-region storage later.
- Admin tools can show tenant region for support and compliance.

## Non-goals (for now)
- Cross-region replication
- Active-active multi-region routing
- Automated tenant migration workflows

## Future Work
- Region-aware DB session routing based on `tenant.data_region`
- Data migration tooling and audit trails for tenant moves
- Region-specific KMS/encryption keys and data plane separation
