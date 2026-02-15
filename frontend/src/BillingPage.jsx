import { useCallback, useEffect, useMemo, useState } from "react";
import { ACTIVE_TENANT_KEY, apiFetch } from "./api";
import { getRoleTemplate } from "./roles";

const PLAN_OPTIONS = [
  {
    key: "pro",
    name: "Pro",
    price: "$249 / month",
    highlight: "Revenue leak heatmaps, remediation workspace, and verification.",
    features: [
      "10 websites",
      "30-day retention + geo history",
      "City-level geo and trust scoring",
      "Remediation playbooks + verification",
    ],
  },
  {
    key: "business",
    name: "Business",
    price: "$399 / month",
    highlight: "SSO, data exports, and advanced alerting thresholds.",
    features: [
      "25 websites",
      "90-day geo history + ASN detail",
      "Advanced alerting + exports",
      "Role templates + priority support",
    ],
  },
  {
    key: "enterprise",
    name: "Enterprise",
    price: "Custom",
    highlight: "SCIM/SAML, legal hold, and dedicated region options.",
    features: [
      "Unlimited websites",
      "Custom retention + legal hold",
      "SCIM + SAML provisioning",
      "Dedicated success + SLA",
    ],
  },
];

function navigateTo(path) {
  if (!path) return;
  window.history.pushState({}, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

function formatDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString();
}

export default function BillingPage() {
  const [tenants, setTenants] = useState([]);
  const [activeTenant, setActiveTenant] = useState(
    localStorage.getItem(ACTIVE_TENANT_KEY) || ""
  );
  const [activeRole, setActiveRole] = useState(null);
  const [loadingPlan, setLoadingPlan] = useState("");
  const [loadingPortal, setLoadingPortal] = useState(false);
  const [loadingStatus, setLoadingStatus] = useState(false);
  const [error, setError] = useState("");
  const [statusMessage, setStatusMessage] = useState("");
  const [billingStatus, setBillingStatus] = useState(null);

  const roleTemplate = useMemo(() => getRoleTemplate(activeRole), [activeRole]);

  const fallbackCanManage = useMemo(
    () => ["owner", "admin", "billing_admin"].includes(String(activeRole || "").toLowerCase()),
    [activeRole]
  );
  const canManage = billingStatus ? Boolean(billingStatus.can_manage_billing) : fallbackCanManage;

  const currentPlanKey = useMemo(() => {
    if (!billingStatus?.plan_key) return "";
    return String(billingStatus.plan_key).toLowerCase();
  }, [billingStatus]);

  const availabilityByPlan = useMemo(() => {
    const map = new Map();
    for (const option of billingStatus?.available_plans || []) {
      map.set(String(option.plan_key || "").toLowerCase(), option);
    }
    return map;
  }, [billingStatus]);

  const loadTenants = useCallback(async () => {
    try {
      const resp = await apiFetch("/api/v1/tenants");
      if (!resp.ok) {
        throw new Error("Unable to load tenants");
      }
      const data = await resp.json();
      setTenants(Array.isArray(data) ? data : []);
      if (!activeTenant && data.length) {
        const first = data[0];
        setActiveTenant(first.slug);
        localStorage.setItem(ACTIVE_TENANT_KEY, String(first.slug));
      }
    } catch (err) {
      setError(err.message || "Unable to load tenants");
    }
  }, [activeTenant]);

  const loadActiveRole = useCallback(async () => {
    if (!activeTenant) return;
    try {
      const resp = await apiFetch("/api/v1/me", { skipReauth: true });
      if (!resp.ok) {
        throw new Error("Unable to load role");
      }
      const data = await resp.json();
      setActiveRole(data?.active_role || null);
    } catch (err) {
      setActiveRole(null);
    }
  }, [activeTenant]);

  const loadBillingStatus = useCallback(async () => {
    if (!activeTenant) {
      setBillingStatus(null);
      return;
    }
    setLoadingStatus(true);
    try {
      const resp = await apiFetch("/api/v1/billing/status", { skipReauth: true });
      if (!resp.ok) {
        const payload = await resp.json().catch(() => ({}));
        throw new Error(payload?.detail || "Unable to load billing status");
      }
      const data = await resp.json();
      setBillingStatus(data);
    } catch (err) {
      setBillingStatus(null);
      setError(err.message || "Unable to load billing status");
    } finally {
      setLoadingStatus(false);
    }
  }, [activeTenant]);

  useEffect(() => {
    loadTenants();
  }, [loadTenants]);

  useEffect(() => {
    if (!activeTenant) {
      localStorage.removeItem(ACTIVE_TENANT_KEY);
      setBillingStatus(null);
      return;
    }
    localStorage.setItem(ACTIVE_TENANT_KEY, activeTenant);
    loadActiveRole();
    loadBillingStatus();
  }, [activeTenant, loadActiveRole, loadBillingStatus]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const checkout = (params.get("checkout") || "").toLowerCase();
    if (!checkout) return;

    if (checkout === "success") {
      setStatusMessage("Checkout completed. Subscription status refreshed.");
      if (activeTenant) {
        void loadBillingStatus();
      }
    } else if (checkout === "cancel") {
      setStatusMessage("Checkout canceled. No changes were made to your plan.");
    }

    params.delete("checkout");
    const nextQuery = params.toString();
    const nextUrl = `${window.location.pathname}${nextQuery ? `?${nextQuery}` : ""}`;
    window.history.replaceState({}, "", nextUrl);
  }, [activeTenant, loadBillingStatus]);

  const handleCheckout = async (planKey) => {
    if (!canManage) {
      setError("Owner, admin, or billing admin role required to upgrade.");
      return;
    }

    const availability = availabilityByPlan.get(String(planKey).toLowerCase());
    if (availability && !availability.checkout_available && !availability.contact_sales) {
      setError("Checkout is not configured for this plan yet.");
      return;
    }

    setLoadingPlan(planKey);
    setError("");
    setStatusMessage("");
    try {
      const resp = await apiFetch("/api/v1/billing/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ plan_key: planKey }),
      });
      if (!resp.ok) {
        const detail = await resp.json().catch(() => null);
        throw new Error(detail?.detail || "Unable to start checkout");
      }
      const data = await resp.json();
      if (!data?.checkout_url) {
        throw new Error("Checkout URL missing");
      }
      window.location.assign(data.checkout_url);
    } catch (err) {
      setError(err.message || "Unable to start checkout");
    } finally {
      setLoadingPlan("");
    }
  };

  const handlePortal = async () => {
    if (!canManage) {
      setError("Owner, admin, or billing admin role required to manage billing.");
      return;
    }
    setLoadingPortal(true);
    setError("");
    setStatusMessage("");
    try {
      const resp = await apiFetch("/api/v1/billing/portal", { method: "POST" });
      if (!resp.ok) {
        const detail = await resp.json().catch(() => null);
        throw new Error(detail?.detail || "Unable to open billing portal");
      }
      const data = await resp.json();
      if (!data?.portal_url) {
        throw new Error("Portal URL missing");
      }
      window.location.assign(data.portal_url);
    } catch (err) {
      setError(err.message || "Unable to open billing portal");
    } finally {
      setLoadingPortal(false);
    }
  };

  return (
    <div className="stack">
      <section className="card billing-header">
        <div>
          <h2 className="section-title">Billing & Plans</h2>
          <p className="subtle">
            Upgrade your tier, manage subscriptions, and unlock advanced protections.
          </p>
          {activeRole && (
            <div className="help" title={roleTemplate?.description || ""}>
              Role: {roleTemplate?.label || activeRole}
            </div>
          )}
          {billingStatus && (
            <p className="subtle small" data-testid="billing-current-plan">
              Current plan: {billingStatus.plan_name || "Free"}
              {billingStatus.subscription_status
                ? ` | Status: ${billingStatus.subscription_status}`
                : ""}
              {billingStatus.current_period_end
                ? ` | Renews: ${formatDate(billingStatus.current_period_end)}`
                : ""}
            </p>
          )}
        </div>
        <div className="billing-tenant">
          <label className="label">Active tenant</label>
          <select
            className="select"
            value={activeTenant}
            onChange={(e) => setActiveTenant(e.target.value)}
          >
            <option value="">Select tenant</option>
            {tenants.map((tenant) => (
              <option key={tenant.id} value={tenant.slug}>
                {tenant.name}
              </option>
            ))}
          </select>
        </div>
      </section>

      <section className="card">
        <div className="billing-actions">
          <button
            className="btn secondary"
            onClick={handlePortal}
            disabled={loadingPortal || !canManage}
          >
            {loadingPortal ? "Opening portal..." : "Manage subscription"}
          </button>
          <button
            className="btn secondary"
            onClick={() => navigateTo("/dashboard/onboarding")}
          >
            Connect website
          </button>
          <button
            className="btn secondary"
            onClick={() => loadBillingStatus()}
            disabled={loadingStatus}
          >
            {loadingStatus ? "Refreshing..." : "Refresh status"}
          </button>
          {!canManage && (
            <span className="help">
              Owner, admin, or billing admin role required for billing actions.
            </span>
          )}
        </div>
        {error && <p className="error-text">{error}</p>}
        {statusMessage && <p className="help">{statusMessage}</p>}
        {billingStatus && !billingStatus.stripe_configured && (
          <p className="help">Stripe checkout is not configured yet. Contact support to enable paid plans.</p>
        )}
      </section>

      <section className="billing-grid">
        {PLAN_OPTIONS.map((plan) => {
          const availability = availabilityByPlan.get(plan.key) || null;
          const isCurrent = currentPlanKey === plan.key;
          const isEnterprise = plan.key === "enterprise";
          const checkoutAvailable = availability
            ? availability.checkout_available
            : !isEnterprise;
          const contactSales = availability
            ? availability.contact_sales
            : isEnterprise;
          const disabled =
            !canManage ||
            loadingPlan === plan.key ||
            isCurrent ||
            (!checkoutAvailable && !contactSales);

          return (
            <div key={plan.key} className="card billing-plan">
              <div className="billing-plan-header">
                <div>
                  <h3 className="section-title">{plan.name}</h3>
                  <div className="billing-price">{plan.price}</div>
                </div>
                <button
                  className="btn primary"
                  onClick={() => {
                    if (contactSales) {
                      window.location.href = "mailto:enterprise@apishield.plus";
                    } else {
                      void handleCheckout(plan.key);
                    }
                  }}
                  disabled={disabled}
                >
                  {isCurrent
                    ? "Current plan"
                    : contactSales
                    ? "Contact sales"
                    : loadingPlan === plan.key
                    ? "Starting checkout..."
                    : checkoutAvailable
                    ? "Upgrade"
                    : "Unavailable"}
                </button>
              </div>
              <p className="subtle">{plan.highlight}</p>
              <ul className="billing-features">
                {plan.features.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          );
        })}
      </section>
    </div>
  );
}
