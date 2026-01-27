import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "./api";

const STATUS_OPTIONS = ["operational", "degraded", "outage"];
const INCIDENT_STATUSES = ["investigating", "identified", "monitoring", "resolved"];
const IMPACT_OPTIONS = ["minor", "major", "critical"];

function AdminStatusPage() {
  const [components, setComponents] = useState([]);
  const [incidents, setIncidents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [accessDenied, setAccessDenied] = useState(false);

  const [newIncident, setNewIncident] = useState({
    title: "",
    status: "investigating",
    impact_level: "minor",
    components: "api",
    message: "",
    is_published: false,
  });
  const [updateDrafts, setUpdateDrafts] = useState({});
  const [updateStatuses, setUpdateStatuses] = useState({});

  const loadStatus = async () => {
    setLoading(true);
    setError(null);
    setAccessDenied(false);
    try {
      const [componentResp, incidentResp] = await Promise.all([
        apiFetch("/api/v1/admin/status/components"),
        apiFetch("/api/v1/admin/status/incidents"),
      ]);
      if (componentResp.status === 403 || incidentResp.status === 403) {
        setAccessDenied(true);
        setComponents([]);
        setIncidents([]);
        return;
      }
      const componentData = componentResp.ok ? await componentResp.json() : [];
      const incidentData = incidentResp.ok ? await incidentResp.json() : [];
      setComponents(componentData || []);
      setIncidents(incidentData || []);
    } catch (err) {
      console.error("admin status load failed", err);
      setError("Unable to load status data.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStatus();
  }, []);

  const handleComponentStatusChange = async (componentId, status) => {
    try {
      const resp = await apiFetch(`/api/v1/admin/status/components/${componentId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ current_status: status }),
      });
      if (!resp.ok) {
        throw new Error("Failed to update component");
      }
      await loadStatus();
    } catch (err) {
      console.error(err);
      setError("Failed to update component status.");
    }
  };

  const handleCreateIncident = async () => {
    const components = newIncident.components
      .split(",")
      .map((part) => part.trim())
      .filter(Boolean);
    try {
      const resp = await apiFetch("/api/v1/admin/status/incidents", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: newIncident.title,
          status: newIncident.status,
          impact_level: newIncident.impact_level,
          components_affected: components,
          message: newIncident.message || undefined,
          is_published: newIncident.is_published,
        }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        throw new Error(body.detail || "Failed to create incident");
      }
      setNewIncident({
        title: "",
        status: "investigating",
        impact_level: "minor",
        components: "api",
        message: "",
        is_published: false,
      });
      await loadStatus();
    } catch (err) {
      console.error(err);
      setError(err.message || "Failed to create incident.");
    }
  };

  const handlePublishToggle = async (incident) => {
    const path = incident.is_published
      ? `/api/v1/admin/status/incidents/${incident.id}/unpublish`
      : `/api/v1/admin/status/incidents/${incident.id}/publish`;
    try {
      const resp = await apiFetch(path, { method: "POST" });
      if (!resp.ok) {
        throw new Error("Failed to update publish state");
      }
      await loadStatus();
    } catch (err) {
      console.error(err);
      setError("Failed to update publish state.");
    }
  };

  const handleIncidentUpdate = async (incidentId) => {
    const message = updateDrafts[incidentId];
    if (!message) return;
    const statusValue = updateStatuses[incidentId] || undefined;
    try {
      const resp = await apiFetch(`/api/v1/admin/status/incidents/${incidentId}/updates`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, status: statusValue }),
      });
      if (!resp.ok) {
        throw new Error("Failed to post update");
      }
      setUpdateDrafts((prev) => ({ ...prev, [incidentId]: "" }));
      setUpdateStatuses((prev) => ({ ...prev, [incidentId]: "" }));
      await loadStatus();
    } catch (err) {
      console.error(err);
      setError("Failed to post incident update.");
    }
  };

  const componentKeys = useMemo(
    () => components.map((component) => component.key).join(", ") || "api, ingest, geo",
    [components]
  );

  if (accessDenied) {
    return (
      <section className="card">
        <h2 className="section-title">Status Ops</h2>
        <p>Access denied. Platform admin privileges required.</p>
      </section>
    );
  }

  return (
    <section className="card admin-status-page">
      <div className="row space-between align-center">
        <div>
          <h2 className="section-title">Status Ops</h2>
          <p className="muted">
            Update public component status and publish incident updates.
          </p>
        </div>
        <button className="btn secondary" onClick={loadStatus}>
          Refresh
        </button>
      </div>

      {error && <p className="error">{error}</p>}
      {loading && <p className="muted">Loading...</p>}

      <div className="admin-status-grid">
        <div>
          <h3>Components</h3>
          <div className="status-component-list">
            {components.map((component) => (
              <div className="status-component-row" key={component.id}>
                <div>
                  <strong>{component.display_name}</strong>
                  <div className="muted small">{component.key}</div>
                </div>
                <select
                  className="select"
                  value={component.current_status}
                  onChange={(e) => handleComponentStatusChange(component.id, e.target.value)}
                >
                  {STATUS_OPTIONS.map((status) => (
                    <option key={status} value={status}>
                      {status}
                    </option>
                  ))}
                </select>
              </div>
            ))}
          </div>
        </div>

        <div>
          <h3>Create Incident</h3>
          <div className="status-form">
            <div className="field">
              <label htmlFor="incident-title">Title</label>
              <input
                id="incident-title"
                className="input"
                value={newIncident.title}
                onChange={(e) => setNewIncident({ ...newIncident, title: e.target.value })}
              />
            </div>
            <div className="status-form-row">
              <div className="field">
                <label>Status</label>
                <select
                  className="select"
                  value={newIncident.status}
                  onChange={(e) => setNewIncident({ ...newIncident, status: e.target.value })}
                >
                  {INCIDENT_STATUSES.map((status) => (
                    <option key={status} value={status}>
                      {status}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label>Impact</label>
                <select
                  className="select"
                  value={newIncident.impact_level}
                  onChange={(e) => setNewIncident({ ...newIncident, impact_level: e.target.value })}
                >
                  {IMPACT_OPTIONS.map((impact) => (
                    <option key={impact} value={impact}>
                      {impact}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="field">
              <label>Components ({componentKeys})</label>
              <input
                className="input"
                value={newIncident.components}
                onChange={(e) => setNewIncident({ ...newIncident, components: e.target.value })}
              />
            </div>
            <div className="field">
              <label>Initial update</label>
              <textarea
                className="textarea"
                rows="3"
                value={newIncident.message}
                onChange={(e) => setNewIncident({ ...newIncident, message: e.target.value })}
              />
            </div>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={newIncident.is_published}
                onChange={(e) => setNewIncident({ ...newIncident, is_published: e.target.checked })}
              />
              Publish immediately
            </label>
            <button className="btn primary" onClick={handleCreateIncident}>
              Create Incident
            </button>
          </div>
        </div>
      </div>

      <div className="status-incidents-admin">
        <h3>Incidents</h3>
        {incidents.length === 0 ? (
          <p className="muted">No incidents created yet.</p>
        ) : (
          incidents.map((incident) => (
            <div className="status-incident-admin" key={incident.id}>
              <div className="row space-between align-center">
                <div>
                  <strong>{incident.title}</strong>
                  <div className="muted small">
                    {incident.status} - {incident.impact_level} -
                    {incident.components_affected.join(", ") || "N/A"}
                  </div>
                </div>
                <button
                  className={`btn small ${incident.is_published ? "secondary" : "primary"}`}
                  onClick={() => handlePublishToggle(incident)}
                >
                  {incident.is_published ? "Unpublish" : "Publish"}
                </button>
              </div>
              <div className="status-update-form">
                <textarea
                  className="textarea"
                  rows="2"
                  placeholder="Post an update message"
                  value={updateDrafts[incident.id] || ""}
                  onChange={(e) =>
                    setUpdateDrafts((prev) => ({ ...prev, [incident.id]: e.target.value }))
                  }
                />
                <div className="status-update-actions">
                  <select
                    className="select"
                    value={updateStatuses[incident.id] || ""}
                    onChange={(e) =>
                      setUpdateStatuses((prev) => ({ ...prev, [incident.id]: e.target.value }))
                    }
                  >
                    <option value="">Keep status</option>
                    {INCIDENT_STATUSES.map((status) => (
                      <option key={status} value={status}>
                        {status}
                      </option>
                    ))}
                  </select>
                  <button
                    className="btn secondary"
                    onClick={() => handleIncidentUpdate(incident.id)}
                  >
                    Post update
                  </button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </section>
  );
}

export default AdminStatusPage;
