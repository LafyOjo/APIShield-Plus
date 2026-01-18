# ADR 0001: Multi-tenancy with shared DB and tenant_id scoping
Status: Proposed  
Date: 2026-01-11

## Problem
APIShield+ must support multiple tenants (orgs) without data leakage. The current code assumes a single tenant (global alerts/events, global config/security switches, global WebSocket listeners, global in-memory counters, no tenant selection in frontend). We need a clear architecture and rules so the migration in Section 1 stays consistent.

## Options considered
- **Separate DB per tenant:** strong isolation, costly to operate; migrations and query fan-out complexity; heavy for small demo footprint.  
- **Schema-per-tenant:** better packing but still complex migrations and connection churn; doesn't fit SQLite dev flow.  
- **Shared DB + tenant_id column:** simplest to ship in this repo; single schema, cheaper operations; requires strict query discipline and good tests.

## Decision
Use **shared database with tenant_id on every tenant-owned row**. Reads/writes require tenant context except platform metadata. This matches current lightweight stack (SQLite dev, single app instance) and keeps the migration tractable for Section 1.

## Tenancy model
- Add `tenant_id` to tenant-owned tables: policies, alerts, audit_logs, access_logs, auth_events, events (and future tables).  
- Users are **global** and linked via Membership join: `membership(user_id, tenant_id, role)` (see ADR 0002).  
- Roles are **per tenant**: owner, admin, analyst, viewer. No global admin beyond platform ops.

## Active tenant resolution
- **Chosen:** `X-Tenant-ID` header provided by frontend. Backend dependency resolves membership and rejects if missing/unauthorized.  
- JWTs remain user-scoped; tenant stays explicit per request for simplicity and easy rotation.  
- Optional JWT hint: include a small `memberships` snapshot (`tenant_id`, `role`) for UI convenience only; backend **never** trusts it for authorization because it can be stale.  
- If absent: return 400 for tenant-required endpoints. Cross-tenant access must 404/403 without revealing existence.

## Security posture & isolation rules
- **DB queries:** Never fetch tenant-owned objects without filtering on tenant_id. Require `(id, tenant_id)` in lookups.  
- **WebSockets:** No global listener lists; connections must authenticate and bind to a tenant. Broadcast only within that tenant's channel.  
- **Audit/events/logs:** Store tenant_id on write; emit/stream only rows for the active tenant.  
- **Rate limiting / in-memory state:** Key all caches/counters (e.g., failed attempts, chain tokens) by tenant_id (and user_id as needed).  
- **Config/security switches:** Security toggles and thresholds are tenant-scoped; platform-wide changes are explicit and rare.  
- **Metrics:** Avoid high-cardinality tenant labels. Aggregate per tenant only for low-volume metrics; otherwise expose platform-wide metrics without tenant label or sample a safe subset.

## Implementation outline (Section 1 scope)
- Add tenant_id columns + FKs + indexes; make `(tenant_id, username)` unique.  
- Add `tenants` and `memberships` models/CRUD.  
- Add `require_tenant_context()` dependency that: (a) authenticates user, (b) reads X-Tenant-ID, (c) checks membership/role, (d) returns tenant_id + role.  
- Add `scoped_query(model, tenant_id)` helper (or small wrappers) to centralize tenant filtering.  
- Thread tenant_id through CRUD functions and schemas; reject calls missing tenant_id on tenant-owned operations.  
- Update WebSocket handlers to include tenant resolution and listener partitioning by tenant.  
- Update in-memory structures (`FAILED_USER_ATTEMPTS`, chain tokens) to be keyed by tenant.  
- Frontend: add workspace selector, persist active tenant, send X-Tenant-ID on all calls, and block UI until a tenant is selected.

## DB index checklist
- Every tenant-owned table has an index starting with `tenant_id` (single-column or composite).
- Composite indexes cover frequent lookups:
  - memberships: `(tenant_id, user_id)`
  - invites: `(tenant_id, email)`, `(tenant_id, expires_at)`
  - api_keys: `(tenant_id, environment_id)`
  - domain_verifications: `(tenant_id, website_id)`
  - websites: `(tenant_id, created_at)`
  - tenant_usage: `(tenant_id, period_start)`
- Avoid redundant indexes that duplicate left-most prefixes unless justified by read hot paths.
- Migrations must create/drop indexes explicitly (no implicit ORM-only changes).

## Tests to add (not implemented yet)
- Cross-tenant access returns 404/403 for alerts/events/logs by id and list endpoints.  
- WebSocket client from tenant A never receives events for tenant B.  
- Rate-limit counters isolated per tenant (A's failures don't block B).  
- Lint/check: ensure all CRUD/query helpers include tenant_id in filters.  
- Header resolver rejects missing or unauthorized tenant_id.

## Non-goals for Section 1
- SSO/OIDC multi-tenant federation, SCIM, SOC2 controls.  
- Per-tenant billing, usage caps, or dedicated infra.  
- Data residency / encryption redesign.  
- Full self-service tenant lifecycle UI (basic creation/assignment is enough).

## Consequences
- **Positive:** Minimal operational overhead; fast path to multi-tenant without infra changes; consistent rulebook for scoping.  
- **Trade-offs:** Requires disciplined query patterns and tests; potential tenant label cardinality concerns in metrics; header-based tenant context can be mis-set by buggy clients, mitigated by strict membership check.

## Implementation checklist (guardrails)
- [ ] Tenant tables/columns and `(tenant_id, username)` uniqueness created.  
- [ ] `require_tenant_context()` added and used on all tenant-owned endpoints.  
- [ ] `scoped_query`/CRUD helpers enforce tenant filters by default.  
- [ ] WebSockets partitioned by tenant; broadcast uses tenant_id.  
- [ ] In-memory counters and security chain keyed by tenant_id.  
- [ ] Postgres trigger `enforce_membership_owner_invariant` prevents removing/demoting the last owner.  
- [ ] Frontend sends `X-Tenant-ID` and blocks access until a tenant is selected.  
- [ ] Tests cover cross-tenant 404/403, websocket isolation, counter isolation, and lint for tenant filters.  
- [ ] Metrics strategy documented to avoid tenant_id cardinality explosion.
