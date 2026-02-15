# APIShield+ SaaS Service Rollout

This checklist turns the current product into a self-serve paid service.

## 1) Prerequisites

Backend env vars:

- `SECRET_KEY`
- `DATABASE_URL`
- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `STRIPE_PRICE_ID_PRO`
- `STRIPE_PRICE_ID_BUSINESS`
- `STRIPE_PRICE_ID_ENTERPRISE`
- `APP_BASE_URL` (for Stripe return URLs)

Install backend deps (includes Stripe SDK):

```bash
pip install -r backend/requirements.txt
```

## 2) User flow now supported

1. User opens login screen and switches to **Sign up**.
2. Registration creates user + default workspace.
3. App auto-signs in and redirects to onboarding (`/dashboard/onboarding`).
4. User connects website (domain + environment + key/snippet).
5. User opens billing (`/billing`) and upgrades plan.
6. Stripe webhook updates subscription + entitlements.

## 3) Stripe wiring

- Checkout endpoint: `POST /api/v1/billing/checkout`
- Portal endpoint: `POST /api/v1/billing/portal`
- Webhook endpoint: `POST /api/v1/billing/webhook`
- Status endpoint: `GET /api/v1/billing/status`

Use Stripe CLI in dev:

```bash
stripe listen --forward-to http://localhost:8000/api/v1/billing/webhook
```

## 4) Tenant-scoped billing behavior

- Billing APIs are tenant-scoped via `X-Tenant-ID`.
- Billing management requires `owner`, `admin`, or `billing_admin`.
- Read-only users can still view billing status (`/api/v1/billing/status`) but cannot checkout.

## 5) Production checks

- Enforce HTTPS and secure headers in edge/proxy.
- Verify webhook signature in production with `STRIPE_WEBHOOK_SECRET`.
- Confirm audit logs for checkout/webhook events.
- Validate plan entitlements after upgrade/downgrade.

## 6) Recommended go-live test

1. Create a new account via Sign up.
2. Complete onboarding website setup.
3. Run checkout to Pro and complete payment in Stripe test mode.
4. Confirm `/api/v1/billing/status` shows updated plan/status.
5. Confirm newly unlocked Pro features are available in UI.
