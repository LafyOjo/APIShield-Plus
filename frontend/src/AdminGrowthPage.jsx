import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "./api";

const formatDate = (value) => {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleDateString();
};

const formatPercent = (value) => {
  if (value == null || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(1)}%`;
};

const riskClass = (value) => {
  if (value === "high") return "risk-high";
  if (value === "medium") return "risk-medium";
  return "risk-low";
};

export default function AdminGrowthPage() {
  const [snapshots, setSnapshots] = useState([]);
  const [latest, setLatest] = useState(null);
  const [cohorts, setCohorts] = useState([]);
  const [paywall, setPaywall] = useState([]);
  const [churnRisk, setChurnRisk] = useState([]);
  const [loading, setLoading] = useState(false);
  const [accessDenied, setAccessDenied] = useState(false);
  const [error, setError] = useState("");

  const loadGrowth = async (refresh = false) => {
    setLoading(true);
    setError("");
    setAccessDenied(false);
    try {
      const resp = await apiFetch(`/api/v1/admin/growth?days=30${refresh ? "&refresh=true" : ""}`);
      if (resp.status === 403) {
        setAccessDenied(true);
        return;
      }
      if (!resp.ok) {
        throw new Error("Unable to load growth analytics");
      }
      const data = await resp.json();
      setSnapshots(data.snapshots || []);
      setLatest(data.latest || null);
      setCohorts(data.cohorts || []);
      setPaywall(data.paywall || []);
      setChurnRisk(data.churn_risk || []);
    } catch (err) {
      setError(err.message || "Unable to load growth analytics");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadGrowth(true);
  }, []);

  const funnelSteps = useMemo(() => {
    if (!latest?.funnel) return [];
    const funnel = latest.funnel || {};
    return [
      { key: "signups", label: "Signups", value: funnel.signups || 0 },
      { key: "activated", label: "First event", value: funnel.activated || 0 },
      { key: "onboarding_completed", label: "Onboarding done", value: funnel.onboarding_completed || 0 },
      { key: "first_incident", label: "First incident", value: funnel.first_incident || 0 },
      { key: "first_prescription", label: "First remediation", value: funnel.first_prescription || 0 },
      { key: "upgraded", label: "Upgraded", value: funnel.upgraded || 0 },
    ];
  }, [latest]);

  if (accessDenied) {
    return (
      <section className="card">
        <h2 className="section-title">Growth Analytics</h2>
        <p>Access denied. Platform admin privileges required.</p>
      </section>
    );
  }

  return (
    <div className="stack">
      <section className="card growth-header">
        <div>
          <h2 className="section-title">Growth Analytics</h2>
          <p className="muted">
            Track activation, upgrade conversion, cohorts, and churn risk signals.
          </p>
        </div>
        <button className="btn secondary" onClick={() => loadGrowth(true)}>
          Refresh
        </button>
      </section>

      {loading && <p className="muted">Loading…</p>}
      {error && <p className="error-text">{error}</p>}

      {latest && (
        <section className="growth-summary-grid">
          <div className="card">
            <div className="muted">Signups</div>
            <strong>{latest.signups}</strong>
          </div>
          <div className="card">
            <div className="muted">Activated</div>
            <strong>{latest.activated}</strong>
          </div>
          <div className="card">
            <div className="muted">Upgraded</div>
            <strong>{latest.upgraded}</strong>
          </div>
          <div className="card">
            <div className="muted">Churned</div>
            <strong>{latest.churned}</strong>
          </div>
        </section>
      )}

      {funnelSteps.length > 0 && (
        <section className="card">
          <h3 className="section-title">Activation funnel</h3>
          <div className="growth-funnel">
            {funnelSteps.map((step) => (
              <div key={step.key} className="growth-funnel-row">
                <span>{step.label}</span>
                <div className="growth-funnel-track">
                  <div
                    className="growth-funnel-fill"
                    style={{
                      width: `${latest?.signups ? (step.value / latest.signups) * 100 : 0}%`,
                    }}
                  />
                </div>
                <span>{step.value}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="growth-grid">
        <div className="card">
          <h3 className="section-title">Cohort activation</h3>
          <table className="table">
            <thead>
              <tr>
                <th>Week</th>
                <th>Tenants</th>
                <th>Activated</th>
                <th>Upgraded</th>
              </tr>
            </thead>
            <tbody>
              {cohorts.map((cohort) => (
                <tr key={cohort.week_start}>
                  <td>{cohort.week_start}</td>
                  <td>{cohort.total}</td>
                  <td>{formatPercent(cohort.activation_rate)}</td>
                  <td>{formatPercent(cohort.upgrade_rate)}</td>
                </tr>
              ))}
              {!cohorts.length && !loading && (
                <tr>
                  <td colSpan="4" className="muted">
                    No cohort data available yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="card">
          <h3 className="section-title">Paywall conversion</h3>
          <table className="table">
            <thead>
              <tr>
                <th>Feature</th>
                <th>Source</th>
                <th>Shown</th>
                <th>CTA</th>
                <th>Checkout</th>
                <th>Upgrades</th>
              </tr>
            </thead>
            <tbody>
              {paywall.map((row, idx) => (
                <tr key={`${row.feature_key}-${row.source}-${idx}`}>
                  <td>{row.feature_key}</td>
                  <td>{row.source || "—"}</td>
                  <td>{row.shown}</td>
                  <td>{row.cta_clicked}</td>
                  <td>{row.checkout_started}</td>
                  <td>{row.upgrades}</td>
                </tr>
              ))}
              {!paywall.length && !loading && (
                <tr>
                  <td colSpan="6" className="muted">
                    No paywall telemetry captured yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card">
        <h3 className="section-title">Churn risk watchlist</h3>
        <table className="table">
          <thead>
            <tr>
              <th>Tenant</th>
              <th>Last event (days)</th>
              <th>Last login (days)</th>
              <th>Open incidents</th>
              <th>Risk</th>
            </tr>
          </thead>
          <tbody>
            {churnRisk.map((item) => (
              <tr key={item.tenant_id}>
                <td>
                  <strong>{item.tenant_name}</strong>
                  <div className="muted small">{item.tenant_slug}</div>
                </td>
                <td>{item.days_since_last_event ?? "—"}</td>
                <td>{item.days_since_last_login ?? "—"}</td>
                <td>{item.open_incidents}</td>
                <td>
                  <span className={`risk-chip ${riskClass(item.risk_level)}`}>
                    {item.risk_level}
                  </span>
                </td>
              </tr>
            ))}
            {!churnRisk.length && !loading && (
              <tr>
                <td colSpan="5" className="muted">
                  No churn risk signals detected yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>

      <section className="card">
        <h3 className="section-title">Daily snapshots</h3>
        <table className="table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Signups</th>
              <th>Activated</th>
              <th>Upgraded</th>
              <th>Churned</th>
              <th>Avg time to first event</th>
            </tr>
          </thead>
          <tbody>
            {snapshots.map((snap) => (
              <tr key={snap.snapshot_date}>
                <td>{formatDate(snap.snapshot_date)}</td>
                <td>{snap.signups}</td>
                <td>{snap.activated}</td>
                <td>{snap.upgraded}</td>
                <td>{snap.churned}</td>
                <td>{snap.avg_time_to_first_event_seconds?.toFixed?.(0) || "—"}</td>
              </tr>
            ))}
            {!snapshots.length && !loading && (
              <tr>
                <td colSpan="6" className="muted">
                  No snapshots available yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}
