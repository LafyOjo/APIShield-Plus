import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "./api";

const formatDate = (value) => {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString();
};

const formatDuration = (seconds) => {
  if (seconds == null) return "—";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.round(minutes / 60);
  return `${hours}h`;
};

const scoreBucket = (score) => {
  if (score >= 80) return "80-100";
  if (score >= 60) return "60-79";
  if (score >= 40) return "40-59";
  if (score >= 20) return "20-39";
  return "0-19";
};

export default function AdminActivationPage() {
  const [items, setItems] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [accessDenied, setAccessDenied] = useState(false);
  const [error, setError] = useState("");

  const loadActivation = async (refresh = false) => {
    setLoading(true);
    setError("");
    setAccessDenied(false);
    try {
      const resp = await apiFetch(
        `/api/v1/admin/activation?limit=200${refresh ? "&refresh=true" : ""}`
      );
      if (resp.status === 403) {
        setAccessDenied(true);
        setItems([]);
        setSummary(null);
        return;
      }
      if (!resp.ok) {
        throw new Error("Unable to load activation metrics");
      }
      const data = await resp.json();
      setItems(data.items || []);
      setSummary(data.summary || null);
    } catch (err) {
      setError(err.message || "Unable to load activation metrics");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadActivation(true);
  }, []);

  const distribution = useMemo(() => {
    const buckets = {
      "80-100": 0,
      "60-79": 0,
      "40-59": 0,
      "20-39": 0,
      "0-19": 0,
    };
    items.forEach((item) => {
      buckets[scoreBucket(item.activation_score || 0)] += 1;
    });
    return buckets;
  }, [items]);

  if (accessDenied) {
    return (
      <section className="card">
        <h2 className="section-title">Activation Metrics</h2>
        <p>Access denied. Platform admin privileges required.</p>
      </section>
    );
  }

  return (
    <section className="card">
      <div className="row space-between align-center">
        <div>
          <h2 className="section-title">Activation Metrics</h2>
          <p className="muted">Track time-to-first-event and onboarding completion.</p>
        </div>
        <button className="btn secondary" onClick={() => loadActivation(true)}>
          Refresh
        </button>
      </div>

      {loading && <p className="muted">Loading…</p>}
      {error && <p className="error-text">{error}</p>}

      {summary && (
        <div className="activation-summary-grid">
          <div className="card">
            <div className="muted">Tenants tracked</div>
            <strong>{summary.total_tenants || 0}</strong>
          </div>
          <div className="card">
            <div className="muted">With first event</div>
            <strong>{summary.tenants_with_events || 0}</strong>
          </div>
          <div className="card">
            <div className="muted">Onboarding completed</div>
            <strong>{summary.tenants_onboarded || 0}</strong>
          </div>
          <div className="card">
            <div className="muted">Avg time to first event</div>
            <strong>{formatDuration(summary.average_time_to_first_event_seconds)}</strong>
          </div>
        </div>
      )}

      <div className="activation-distribution">
        {Object.entries(distribution).map(([bucket, count]) => (
          <div key={bucket} className="activation-bar">
            <span>{bucket}</span>
            <div className="activation-bar-track">
              <div
                className="activation-bar-fill"
                style={{
                  width: `${items.length ? (count / items.length) * 100 : 0}%`,
                }}
              />
            </div>
            <span>{count}</span>
          </div>
        ))}
      </div>

      <div className="activation-table-wrapper">
        <table className="table">
          <thead>
            <tr>
              <th>Tenant</th>
              <th>Score</th>
              <th>First event</th>
              <th>Onboarding</th>
              <th>Alerts</th>
              <th>Incidents</th>
              <th>Last event</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.tenant_id}>
                <td>
                  <strong>{item.tenant_name}</strong>
                  <div className="muted small">{item.tenant_slug}</div>
                </td>
                <td>{item.activation_score}</td>
                <td>{formatDuration(item.time_to_first_event_seconds)}</td>
                <td>{item.onboarding_completed_at ? "Complete" : "Pending"}</td>
                <td>{item.alerts_count}</td>
                <td>{item.incidents_count}</td>
                <td>{formatDate(item.last_event_at)}</td>
              </tr>
            ))}
            {!items.length && !loading && (
              <tr>
                <td colSpan="7" className="muted">
                  No activation metrics available yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
