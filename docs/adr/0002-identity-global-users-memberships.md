# ADR 0002: Global users with tenant memberships
Status: Accepted  
Date: 2026-01-13

## Problem
APIShield+ is moving to a multi-tenant SaaS model with multiple workspaces per user. We need a single, explicit identity model so tenant isolation, RBAC, and onboarding are consistent across backend and frontend.

## Options considered
- **User has tenant_id (single-tenant users):** Simple, but prevents a user from belonging to multiple tenants. Consultants and shared admin accounts become awkward or impossible.
- **Global User + Membership join (multi-tenant users):** User is global, and a Membership table links users to tenants with roles and status.

## Decision
Use **global Users** with a **Membership** join table that links `user_id ↔ tenant_id` and stores role/status. Roles are per-tenant (owner/admin/analyst/viewer). This aligns with the multi-workspace SaaS requirement and future enterprise features.

## Consequences
- Every tenant-scoped route must validate **membership** for the active tenant.
- The UI must select an **active tenant** and send it on every request.
- Onboarding must create a tenant and an initial owner membership.
- `User.role` is **not** used for tenant authorization; it is legacy/platform-only.

## Active tenant resolution
- Use `X-Tenant-ID` header (see ADR 0001).
- Backend resolves membership for that tenant; lack of membership returns 404/403.
- JWTs remain user-only (no tenant claims for now).

## Must-follow rules
- Never infer tenant from a user record.
- Never query tenant-owned data without a tenant_id filter.
- Role checks are based on Membership role, not User.role.

## Known legacy assumptions to refactor
- `User.role` exists for legacy/admin workflows; it must not gate tenant resources.
- `/api/me` exposes `role` for legacy clients; treat as non-tenant scope.
- Any future endpoint that uses User.role for tenant access is a bug.

## Implementation notes
- Users remain global; no `tenant_id` column on `users`.
- Membership is the single source of truth for tenant access.
