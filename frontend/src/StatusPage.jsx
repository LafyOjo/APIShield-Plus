import { useEffect, useMemo, useState } from "react";
import { API_BASE } from "./api";

const STATUS_API = `${API_BASE || ""}/api/status`;

function formatDate(value) {
  if (!value) return "N/A";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "N/A";
  return date.toLocaleString();
}

function overallStatus(components) {
  if (!components.length) return "operational";
  const statuses = components.map((row) => row.current_status);
  if (statuses.includes("outage")) return "outage";
  if (statuses.includes("degraded")) return "degraded";
  return "operational";
}

function StatusPage() {
  const [components, setComponents] = useState([]);
  const [incidents, setIncidents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const loadStatus = async () => {
    setLoading(true);
    setError(null);
    try {
      const [componentResp, incidentResp] = await Promise.all([
        fetch(`${STATUS_API}/components`),
        fetch(`${STATUS_API}/incidents`),
      ]);
      if (!componentResp.ok) {
        throw new Error("Unable to load status components");
      }
      if (!incidentResp.ok) {
        throw new Error("Unable to load incidents");
      }
      const componentData = await componentResp.json();
      const incidentData = await incidentResp.json();
      setComponents(componentData || []);
      setIncidents(incidentData || []);
    } catch (err) {
      console.error("status fetch failed", err);
      setError("Unable to load status data. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStatus();
  }, []);

  const overall = useMemo(() => overallStatus(components), [components]);

  return (
    <div className="status-page">
      <header className="status-hero">
        <div>
          <p className="status-kicker">APIShield+ Status</p>
          <h1>Service Status</h1>
          <p className="muted">
            Live service health updates for API, ingestion, and dashboard services.
          </p>
        </div>
        <div className="status-hero-actions">
          <span className={`status-pill ${overall}`}>{overall}</span>
          <button className="btn secondary" onClick={loadStatus}>
            Refresh
          </button>
        </div>
      </header>

      {error && (
        <section className="card">
          <p className="error">{error}</p>
        </section>
      )}

      <section className="card">
        <div className="row space-between align-center">
          <h2 className="section-title">Components</h2>
          {loading ? <span className="muted">Updating...</span> : null}
        </div>
        <div className="status-grid">
          {components.map((component) => (
            <div className="status-component" key={component.key}>
              <div>
                <h3>{component.display_name}</h3>
                <p className="muted small">Key: {component.key}</p>
              </div>
              <div className="status-component-meta">
                <span className={`status-pill ${component.current_status}`}>
                  {component.current_status}
                </span>
                <span className="muted small">
                  Updated {formatDate(component.last_updated_at)}
                </span>
              </div>
            </div>
          ))}
          {components.length === 0 && !loading && (
            <p className="muted">No components reported yet.</p>
          )}
        </div>
      </section>

      <section className="card">
        <h2 className="section-title">Incidents</h2>
        {incidents.length === 0 ? (
          <p className="muted">No active incidents. Everything is operating normally.</p>
        ) : (
          <div className="status-incidents">
            {incidents.map((incident) => (
              <div className="status-incident" key={incident.id}>
                <div className="row space-between align-center">
                  <div>
                    <h3>{incident.title}</h3>
                    <p className="muted small">
                      Impact: {incident.impact_level} - Status: {incident.status}
                    </p>
                  </div>
                  <span className={`status-pill ${incident.status}`}>
                    {incident.status}
                  </span>
                </div>
                <p className="muted small">
                  Components: {incident.components_affected.join(", ") || "N/A"}
                </p>
                <div className="status-updates">
                  {(incident.updates || []).map((update, idx) => (
                    <div className="status-update" key={`${incident.id}-${idx}`}>
                      <div className="status-update-time">
                        {formatDate(update.timestamp)}
                      </div>
                      <div>
                        <div className="status-update-message">{update.message}</div>
                        {update.status ? (
                          <span className={`status-pill ${update.status}`}>
                            {update.status}
                          </span>
                        ) : null}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

export default StatusPage;
