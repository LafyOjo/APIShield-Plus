import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch, ACTIVE_TENANT_KEY } from "./api";

const PLAN_OPTIONS = [
  {
    key: "pro",
    name: "Pro",
    price: "$149 / month",
    highlight: "Unlock full geo map, advanced alerts, and prescriptions.",
    features: [
      "30-day geo history",
      "City + ASN attribution",
      "Advanced alerting triggers",
      "Prescriptions and impact estimates",
    ],
  },
  {
    key: "business",
    name: "Business",
    price: "$399 / month",
    highlight: "Extended retention and higher volume limits.",
    features: [
      "90-day geo history",
      "Priority support",
      "Higher ingest limits",
      "Advanced reporting exports",
    ],
  },
];

export default function BillingPage() {
  const [tenants, setTenants] = useState([]);
  const [activeTenant, setActiveTenant] = useState(
    localStorage.getItem(ACTIVE_TENANT_KEY) || ""
  );
  const [activeRole, setActiveRole] = useState(null);
  const [loadingPlan, setLoadingPlan] = useState("");
  const [loadingPortal, setLoadingPortal] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  const canManage = useMemo(
    () => ["admin", "owner"].includes(String(activeRole || "").toLowerCase()),
    [activeRole]
  );

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

  useEffect(() => {
    loadTenants();
  }, [loadTenants]);

  useEffect(() => {
    if (!activeTenant) {
      localStorage.removeItem(ACTIVE_TENANT_KEY);
      return;
    }
    localStorage.setItem(ACTIVE_TENANT_KEY, activeTenant);
    loadActiveRole();
  }, [activeTenant, loadActiveRole]);

  const handleCheckout = async (planKey) => {
    if (!canManage) {
      setError("Admin or owner role required to upgrade.");
      return;
    }
    setLoadingPlan(planKey);
    setError("");
    setStatus("");
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
      setError("Admin or owner role required to manage billing.");
      return;
    }
    setLoadingPortal(true);
    setError("");
    setStatus("");
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
          {!canManage && (
            <span className="help">Admin or owner role required for billing actions.</span>
          )}
        </div>
        {error && <p className="error-text">{error}</p>}
        {status && <p className="help">{status}</p>}
      </section>

      <section className="billing-grid">
        {PLAN_OPTIONS.map((plan) => (
          <div key={plan.key} className="card billing-plan">
            <div className="billing-plan-header">
              <div>
                <h3 className="section-title">{plan.name}</h3>
                <div className="billing-price">{plan.price}</div>
              </div>
              <button
                className="btn primary"
                onClick={() => handleCheckout(plan.key)}
                disabled={loadingPlan === plan.key || !canManage}
              >
                {loadingPlan === plan.key ? "Starting checkout..." : "Upgrade"}
              </button>
            </div>
            <p className="subtle">{plan.highlight}</p>
            <ul className="billing-features">
              {plan.features.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        ))}
      </section>
    </div>
  );
}
