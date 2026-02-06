import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "./api";

const buildRange = () => {
  const to = new Date();
  const from = new Date(to.getTime() - 30 * 24 * 60 * 60 * 1000);
  return { from, to };
};

function PartnerDashboardPage({ partnerProfile, partnerChecked }) {
  const [profile, setProfile] = useState(partnerProfile || null);
  const [metrics, setMetrics] = useState(null);
  const [leads, setLeads] = useState([]);
  const [commissions, setCommissions] = useState([]);
  const [resellerData, setResellerData] = useState(null);
  const [resellerError, setResellerError] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [creatingTenant, setCreatingTenant] = useState(false);
  const [newTenantName, setNewTenantName] = useState("");
  const [newTenantEmail, setNewTenantEmail] = useState("");
  const [newTenantPlan, setNewTenantPlan] = useState("free");

  const range = useMemo(() => buildRange(), []);

  useEffect(() => {
    let active = true;
    if (partnerProfile) {
      setProfile(partnerProfile);
      return () => {
        active = false;
      };
    }
    const loadProfile = async () => {
      try {
        const resp = await apiFetch("/api/v1/partners/me");
        if (!resp.ok) {
          if (active) setProfile(null);
          return;
        }
        const data = await resp.json();
        if (active) setProfile(data);
      } catch (err) {
        if (active) setProfile(null);
      }
    };
    loadProfile();
    return () => {
      active = false;
    };
  }, [partnerProfile]);

  useEffect(() => {
    let active = true;
    if (!profile) {
      setLoading(false);
      return () => {
        active = false;
      };
    }

    const loadData = async () => {
      setLoading(true);
      setError(null);
      try {
        const params = new URLSearchParams({
          from: range.from.toISOString(),
          to: range.to.toISOString(),
        });
        const [metricsResp, leadsResp, commissionResp, resellerResp] = await Promise.all([
          apiFetch(`/api/v1/partners/metrics?${params.toString()}`),
          apiFetch("/api/v1/partners/leads"),
          apiFetch("/api/v1/partners/commissions"),
          apiFetch("/api/v1/reseller/tenants"),
        ]);
        if (!active) return;
        if (!metricsResp.ok) {
          throw new Error("Unable to load metrics");
        }
        const metricsPayload = await metricsResp.json();
        const leadsPayload = leadsResp.ok ? await leadsResp.json() : [];
        const commissionPayload = commissionResp.ok ? await commissionResp.json() : [];
        setMetrics(metricsPayload);
        setLeads(leadsPayload);
        setCommissions(commissionPayload);
        if (resellerResp.ok) {
          const resellerPayload = await resellerResp.json();
          setResellerData(resellerPayload);
          setResellerError(null);
        } else {
          setResellerData(null);
          setResellerError(null);
        }
      } catch (err) {
        if (active) setError(err.message || "Failed to load partner data");
      } finally {
        if (active) setLoading(false);
      }
    };

    loadData();
    return () => {
      active = false;
    };
  }, [profile, range]);

  const handleCreateTenant = async (event) => {
    event.preventDefault();
    if (!newTenantName.trim()) return;
    setCreatingTenant(true);
    setResellerError(null);
    try {
      const resp = await apiFetch("/api/v1/reseller/tenants", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newTenantName.trim(),
          owner_email: newTenantEmail.trim() || null,
          plan_key: newTenantPlan,
        }),
      });
      if (!resp.ok) {
        const payload = await resp.json().catch(() => ({}));
        throw new Error(payload.detail || "Failed to create tenant");
      }
      const data = await resp.json();
      setResellerData((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          tenants: [data.tenant, ...(prev.tenants || [])],
        };
      });
      setNewTenantName("");
      setNewTenantEmail("");
    } catch (err) {
      setResellerError(err.message || "Failed to create tenant");
    } finally {
      setCreatingTenant(false);
    }
  };

  if (partnerChecked && !profile) {
    return (
      <section className="card">
        <h2 className="section-title">Partner access required</h2>
        <p className="muted">Your account is not linked to a partner portal.</p>
      </section>
    );
  }

  if (loading && !metrics) {
    return (
      <section className="card">
        <h2 className="section-title">Loading partner dashboard…</h2>
        <p className="muted">Pulling the latest conversions and commissions.</p>
      </section>
    );
  }

  return (
    <div className="stack">
      <section className="card">
        <div className="partner-summary">
          <div>
            <h2 className="section-title">Performance snapshot</h2>
            <p className="muted">
              Showing the last 30 days · {profile?.partner_name || "Partner"}
            </p>
          </div>
          {error && <div className="pill danger">{error}</div>}
        </div>
        <div className="partner-grid">
          <div className="partner-card">
            <div className="muted">Leads</div>
            <strong>{metrics?.leads ?? 0}</strong>
          </div>
          <div className="partner-card">
            <div className="muted">Signups</div>
            <strong>{metrics?.signups ?? 0}</strong>
          </div>
          <div className="partner-card">
            <div className="muted">Activated</div>
            <strong>{metrics?.activated ?? 0}</strong>
          </div>
          <div className="partner-card">
            <div className="muted">Upgrades</div>
            <strong>{metrics?.conversions ?? 0}</strong>
          </div>
          <div className="partner-card">
            <div className="muted">Commission owed</div>
            <strong>£{(metrics?.commission_owed ?? 0).toFixed(2)}</strong>
          </div>
          <div className="partner-card">
            <div className="muted">Commission paid</div>
            <strong>£{(metrics?.commission_paid ?? 0).toFixed(2)}</strong>
          </div>
        </div>
      </section>

      <section className="card">
        <h3 className="section-title">Recent leads</h3>
        {leads.length === 0 ? (
          <p className="muted">No leads recorded yet.</p>
        ) : (
          <div className="table-wrapper">
            <table className="table partner-table">
              <thead>
                <tr>
                  <th>Lead</th>
                  <th>Status</th>
                  <th>Created</th>
                  <th>Source</th>
                </tr>
              </thead>
              <tbody>
                {leads.map((lead) => (
                  <tr key={lead.lead_id}>
                    <td>{lead.lead_id}</td>
                    <td>{lead.status}</td>
                    <td>{new Date(lead.created_at).toLocaleString()}</td>
                    <td>{lead.source_meta?.utm_campaign || lead.source_meta?.utm_source || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card">
        <h3 className="section-title">Commission ledger</h3>
        {commissions.length === 0 ? (
          <p className="muted">No commission activity yet.</p>
        ) : (
          <div className="table-wrapper">
            <table className="table partner-table">
              <thead>
                <tr>
                  <th>Account</th>
                  <th>Plan</th>
                  <th>Status</th>
                  <th>Conversion</th>
                  <th>Commission</th>
                </tr>
              </thead>
              <tbody>
                {commissions.map((entry) => (
                  <tr key={entry.id}>
                    <td>{entry.tenant_ref}</td>
                    <td>{entry.plan_name || "—"}</td>
                    <td>{entry.status}</td>
                    <td>{entry.conversion_date ? new Date(entry.conversion_date).toLocaleDateString() : "—"}</td>
                    <td>£{Number(entry.amount || 0).toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {resellerData && (
        <section className="card">
          <div className="partner-summary">
            <div>
              <h3 className="section-title">Managed accounts</h3>
              <p className="muted">
                Billing mode: {resellerData.account?.billing_mode || "customer_pays_stripe"}
              </p>
            </div>
            {resellerError && <div className="pill danger">{resellerError}</div>}
          </div>
          {(profile?.role === "reseller_admin" || profile?.role === "admin") && (
            <form className="partner-form" onSubmit={handleCreateTenant}>
              <div className="partner-form-grid">
                <div className="field">
                  <label>Tenant name</label>
                  <input
                    type="text"
                    value={newTenantName}
                    onChange={(event) => setNewTenantName(event.target.value)}
                    placeholder="Acme Corp"
                  />
                </div>
                <div className="field">
                  <label>Owner email (optional)</label>
                  <input
                    type="email"
                    value={newTenantEmail}
                    onChange={(event) => setNewTenantEmail(event.target.value)}
                    placeholder="owner@acme.com"
                  />
                </div>
                <div className="field">
                  <label>Plan</label>
                  <select
                    value={newTenantPlan}
                    onChange={(event) => setNewTenantPlan(event.target.value)}
                  >
                    <option value="free">Free</option>
                    <option value="pro">Pro</option>
                    <option value="business">Business</option>
                    <option value="enterprise">Enterprise</option>
                  </select>
                </div>
              </div>
              <div className="row">
                <button className="btn primary" type="submit" disabled={creatingTenant}>
                  {creatingTenant ? "Creating…" : "Create managed tenant"}
                </button>
              </div>
            </form>
          )}
          {resellerData.tenants?.length ? (
            <div className="table-wrapper">
              <table className="table partner-table">
                <thead>
                  <tr>
                    <th>Tenant</th>
                    <th>Plan</th>
                    <th>Status</th>
                    <th>Activation score</th>
                    <th>Ingest 24h</th>
                  </tr>
                </thead>
                <tbody>
                  {resellerData.tenants.map((tenant) => (
                    <tr key={tenant.tenant_id}>
                      <td>{tenant.tenant_name}</td>
                      <td>{tenant.plan_name || "—"}</td>
                      <td>{tenant.subscription_status || tenant.status}</td>
                      <td>{tenant.activation_score ?? "—"}</td>
                      <td>{tenant.ingest_24h ?? 0}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="muted">No managed tenants yet.</p>
          )}
        </section>
      )}
    </div>
  );
}

export default PartnerDashboardPage;
