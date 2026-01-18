# APIShield+ Single-Tenant Audit (Section 1 Blueprint)
Scope: identify all single-tenant assumptions across backend/api, models/CRUD, and frontend so Section 1 can introduce tenant scoping safely. Route inventory generated via `scripts/list_fastapi_routes.py` (`docs/tenancy/route_inventory.txt`).

## Top 10 highest risk leakage points
1) `backend/app/api/audit.py`: WebSocket `_listeners` is global, so one tenant can receive another tenant's audit events.  
2) `backend/app/api/score.py`: `FAILED_USER_ATTEMPTS` keyed only by `user_id` and IP-only Alert queries; throttling and alerts collapse tenants.  
3) `backend/app/api/config.py` + env `FAIL_LIMIT`: single global config; any admin call exposes/affects all tenants.  
4) `backend/app/api/security.py`: `SECURITY_ENABLED` + chain token are global; one tenant toggles defenses for everyone.  
5) `backend/app/api/alerts.py` / `backend/app/crud/alerts.py`: returns all alerts with no tenant filter; high leakage.  
6) `backend/app/api/events.py` + `backend/app/core/events.py`: event feed not scoped; dashboards see all tenant events.  
7) `backend/app/api/access_logs.py` + `backend/app/core/access_log.py`: logs keyed by username/path only; cross-tenant visibility and username collisions.  
8) `backend/app/api/auth_events.py` + `backend/app/api/credential_stuffing.py`: auth events/stats global; threat intel mixes tenants.  
9) `backend/app/api/auth.py` + models/users/policies: users/policies lack `tenant_id`; usernames must be globally unique, no per-tenant RBAC.  
10) `frontend/src/App.js` + `frontend/src/api.js`: no workspace selector or tenant propagation; every call pulls global data and drives a shared dashboard.

## Findings table
| Area | File(s) | Assumption | Impact | Proposed Fix | Priority |
| --- | --- | --- | --- | --- | --- |
| websocket | backend/app/api/audit.py | `_listeners` is a global broadcast list; no tenant dimension on connect/publish | Cross-tenant audit/event leakage to any connected client | Require tenant on WebSocket connect, partition listeners per tenant, and enforce auth + tenant checks before broadcast | Section 1 |
| backend API | backend/app/api/score.py | In-memory `FAILED_USER_ATTEMPTS` keyed by `user_id`; Alert queries keyed by `ip` only; FAIL_LIMIT env global | Rate limits and alerts bleed across tenants; noisy neighbors can lock or unblock other tenants' users | Key counters by `(tenant_id,user_id)`; store tenant in alerts and filter queries by tenant; pass tenant context into `record_attempt` | Section 1 |
| config | backend/app/api/config.py, backend/app/api/score.py, backend/app/core/config.py | FAIL_LIMIT and other security knobs are global | One tenant's admin view/changes apply to all tenants; config disclosure | Introduce tenant-level security settings (per-tenant fail limits, windows) and require tenant-scoped admin token to read/update | Section 1 |
| config | backend/app/api/security.py | `SECURITY_ENABLED` + chain token are global | One tenant can disable defenses or read chain for others; replay risk across tenants | Namespaced chain/flags per tenant; persist in DB/cache with tenant_id; enforce tenant-scoped admin dependency | Section 1 |
| DB/query | backend/app/api/alerts.py; backend/app/crud/alerts.py; backend/app/models/alerts.py | Alerts table has no `tenant_id`; queries return all rows | Direct cross-tenant leakage in alerts table/chart | Add `tenant_id` column + index; require tenant in CRUD/route filters; enforce tenant from auth context | Section 1 |
| DB/query | backend/app/api/events.py; backend/app/core/events.py; backend/app/crud/events.py; backend/app/models/events.py | Events table lacks tenant; feed is global | Dashboards show other tenants' activity; cross-tenant success/fail stats mixed | Add `tenant_id`; scope whitelist logging and queries; require tenant context in `log_event` callers | Section 1 |
| DB/query | backend/app/api/access_logs.py; backend/app/core/access_log.py; backend/app/crud/access_logs.py; backend/app/models/access_logs.py | Access logs keyed by username/path only; no tenant filter | Admins or colliding usernames can read other tenants' access trails | Add `tenant_id` to model; middleware must attach tenant; queries filter by tenant; return 404 when tenant mismatch | Section 1 |
| DB/query | backend/app/api/auth_events.py; backend/app/api/credential_stuffing.py; backend/app/models/auth_events.py | Auth events/stats global, filtered only by username demo list | Threat analytics and stuffing counts blend tenants; possible disclosure of auth patterns | Add `tenant_id`; restrict stats to requesting tenant; require auth; filter by tenant in both event writes and reads | Section 1 |
| DB/query | backend/app/api/user_stats.py; backend/app/api/last_logins.py; backend/app/models/events.py | Stats and last-login queries read all events | Tenant admins can see other tenants' usage | Tenant ID on events; scope aggregations to tenant; enforce tenant-aware admin dependency | Section 1 |
| identity | backend/app/api/auth.py; backend/app/models/users.py; backend/app/models/policies.py | Users/policies have no tenant; usernames must be global; /api/me returns user without tenant | Cross-tenant username collisions and global admin role | Add tenants table; add `tenant_id` to users/policies; make (tenant_id, username) unique; include tenant in tokens and dependencies | Section 1 |
| frontend | frontend/src/App.js; frontend/src/api.js; frontend/src/ScoreForm.jsx; frontend/src/AlertsTable.jsx; frontend/src/EventsTable.jsx; frontend/src/SecurityToggle.jsx | Dashboard assumes single workspace; API calls lack tenant header/param; global security toggle in UI | Users view/act on shared data; cannot select or isolate tenant context | Add workspace selector; persist active tenant; attach tenant header/query on all calls; hide data until tenant chosen; render per-tenant dashboards | Section 1 |

## Migration map (tenant columns to introduce in Section 1)
- Create `tenants` (or `workspaces`) table and plumb tenant context through auth/session.
- Add `tenant_id` (FK + index) to: `users`, `policies`, `alerts`, `audit_logs`, `access_logs`, `auth_events`, `events`. Make `(tenant_id, username)` unique in `users`; consider `(tenant_id, timestamp)` indexes for logs/events.
- Update in-memory caches (`FAILED_USER_ATTEMPTS`, chain tokens) to be keyed by `(tenant_id, ...)` and reject updates without tenant context.
- Adjust CRUD/helpers to require tenant_id parameters and filter every query; update Pydantic schemas accordingly.

## Route classification (audit completeness)
Full route list captured in `docs/tenancy/route_inventory.txt` via `scripts/list_fastapi_routes.py`. Categorization of current `backend/app/api` routes:
- Global: `POST /score`; `GET /api/alerts`; `GET /api/alerts/stats` (auth but not tenant); `POST /register`; `POST /login`; `POST /api/token`; `GET /api/me`; `POST /logout`; `GET /api/events`; `GET /api/last-logins`; `GET /api/access-logs` (role-limited but cross-tenant); `WS /api/audit/ws`; `POST /api/audit/log`; `POST /events/auth`; `GET /events/auth`; `GET /api/credential-stuffing-stats`.
- Admin-only (platform-level, still single-tenant): `GET /config`; `GET /api/security`; `GET /api/security/chain`; `POST /api/security`; `GET /api/user-calls`.
- No tenant-scoped routes exist yet.
- Audit completeness check: every route above is categorized; run `python scripts/list_fastapi_routes.py` after changes to refresh `route_inventory.txt` and validate coverage.

## Tenant Safety Checklist (gate for future PRs)
- Every DB query and CRUD helper requires `tenant_id` and filters on it; identifiers are validated against tenant ownership before returning data.
- Authentication artifacts (`/api/me`, JWT claims, tokens) carry `tenant_id`; username uniqueness enforced per tenant.
- Cross-tenant access returns 404/403 with no information leakage; routes verify tenant membership before acting.
- WebSockets are authenticated and namespaced per tenant; broadcasts never cross tenant boundaries.
- In-memory or cached state (rate limits, chain tokens, revocation lists) is keyed by tenant; default paths reject writes without tenant context.
- Admin/config/security toggles are tenant-scoped; platform-level operations are explicit and isolated.
- Frontend always selects an active tenant before fetching data and sends tenant context on every call; UI hides data until tenant is chosen.
- Telemetry/metrics export includes tenant labels (or aggregation is tenant-isolated) to avoid cross-tenant stats leakage.
