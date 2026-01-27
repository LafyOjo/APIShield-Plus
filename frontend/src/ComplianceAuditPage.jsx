import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch } from "./api";

const DAY_MS = 24 * 60 * 60 * 1000;

const toInputValue = (date) => {
  if (!date) return "";
  const parsed = new Date(date);
  if (Number.isNaN(parsed.getTime())) return "";
  return parsed.toISOString().slice(0, 16);
};

const toIsoParam = (value) => {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "";
  return parsed.toISOString();
};

const formatDateTime = (value) => {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "";
  return parsed.toLocaleString();
};

const parseFilename = (header) => {
  if (!header) return "";
  const match = header.match(/filename=([^;]+)/i);
  if (!match) return "";
  return match[1].replace(/(^\"|\"$)/g, "");
};

const navigate = (path) => {
  if (window.location.pathname === path) return;
  window.history.pushState({}, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
};

export default function ComplianceAuditPage() {
  const [activeTab, setActiveTab] = useState("export");
  const [fromValue, setFromValue] = useState(() => {
    const from = new Date(Date.now() - 7 * DAY_MS);
    return toInputValue(from);
  });
  const [toValue, setToValue] = useState(() => toInputValue(new Date()));
  const [actor, setActor] = useState("");
  const [action, setAction] = useState("");
  const [resource, setResource] = useState("");
  const [format, setFormat] = useState("csv");
  const [exportStatus, setExportStatus] = useState("");
  const [exporting, setExporting] = useState(false);
  const [retentionRuns, setRetentionRuns] = useState([]);
  const [runsLoading, setRunsLoading] = useState(false);
  const [runsError, setRunsError] = useState("");

  const queryParams = useMemo(() => {
    const params = new URLSearchParams();
    const fromIso = toIsoParam(fromValue);
    const toIso = toIsoParam(toValue);
    if (fromIso) params.set("from", fromIso);
    if (toIso) params.set("to", toIso);
    if (actor.trim()) params.set("actor", actor.trim());
    if (action.trim()) params.set("action", action.trim());
    if (resource.trim()) params.set("resource", resource.trim());
    return params;
  }, [fromValue, toValue, actor, action, resource]);

  const loadRetentionRuns = useCallback(async () => {
    setRunsLoading(true);
    setRunsError("");
    try {
      const params = new URLSearchParams();
      const fromIso = toIsoParam(fromValue);
      const toIso = toIsoParam(toValue);
      if (fromIso) params.set("from", fromIso);
      if (toIso) params.set("to", toIso);
      const resp = await apiFetch(`/api/v1/retention/runs?${params.toString()}`);
      if (!resp.ok) {
        throw new Error(await resp.text());
      }
      const data = await resp.json();
      setRetentionRuns(data || []);
    } catch (err) {
      setRunsError(err.message || "Unable to load retention runs.");
      setRetentionRuns([]);
    } finally {
      setRunsLoading(false);
    }
  }, [fromValue, toValue]);

  useEffect(() => {
    if (activeTab === "retention") {
      loadRetentionRuns();
    }
  }, [activeTab, loadRetentionRuns]);

  const handleExport = async () => {
    setExportStatus("");
    setExporting(true);
    try {
      const params = new URLSearchParams(queryParams.toString());
      params.set("format", format);
      const resp = await apiFetch(`/api/v1/audit/export?${params.toString()}`, {
        method: "GET",
        skipReauth: true,
      });
      if (!resp.ok) {
        const text = await resp.text();
        throw new Error(text || "Export failed.");
      }
      const blob = await resp.blob();
      const disposition = resp.headers.get("Content-Disposition");
      const filename =
        parseFilename(disposition) ||
        `audit-export-${new Date().toISOString().replace(/[:.]/g, "-")}.${format}`;
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(link.href);
      setExportStatus("Export ready.");
    } catch (err) {
      setExportStatus(err.message || "Export failed.");
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="app-container stack">
      <header className="header bar">
        <h1 className="dashboard-header">Compliance & Audit</h1>
        <div className="row">
          <button
            className="btn secondary nav-tab"
            onClick={() => navigate("/dashboard/compliance/retention")}
          >
            Retention policies
          </button>
          <button
            className={`btn secondary nav-tab ${activeTab === "export" ? "active" : ""}`}
            onClick={() => setActiveTab("export")}
          >
            Audit export
          </button>
          <button
            className={`btn secondary nav-tab ${activeTab === "retention" ? "active" : ""}`}
            onClick={() => setActiveTab("retention")}
          >
            Retention evidence
          </button>
        </div>
      </header>

      {activeTab === "export" && (
        <section className="card">
          <h2 className="section-title">Audit export</h2>
          <p className="subtle">
            Export filtered audit logs for compliance reviews. Raw IPs are
            redacted outside retention windows.
          </p>
          <div
            className="grid"
            style={{
              display: "grid",
              gap: "1rem",
              gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
            }}
          >
            <div className="field">
              <label className="label">From</label>
              <input
                className="input"
                type="datetime-local"
                value={fromValue}
                onChange={(e) => setFromValue(e.target.value)}
              />
            </div>
            <div className="field">
              <label className="label">To</label>
              <input
                className="input"
                type="datetime-local"
                value={toValue}
                onChange={(e) => setToValue(e.target.value)}
              />
            </div>
            <div className="field">
              <label className="label">Actor</label>
              <input
                className="input"
                type="text"
                placeholder="alice@company.com"
                value={actor}
                onChange={(e) => setActor(e.target.value)}
              />
            </div>
            <div className="field">
              <label className="label">Action</label>
              <input
                className="input"
                type="text"
                placeholder="auth.login.success"
                value={action}
                onChange={(e) => setAction(e.target.value)}
              />
            </div>
            <div className="field">
              <label className="label">Resource</label>
              <input
                className="input"
                type="text"
                placeholder="/api/v1/websites"
                value={resource}
                onChange={(e) => setResource(e.target.value)}
              />
            </div>
            <div className="field">
              <label className="label">Format</label>
              <select
                className="select"
                value={format}
                onChange={(e) => setFormat(e.target.value)}
              >
                <option value="csv">CSV</option>
                <option value="json">JSON</option>
              </select>
            </div>
          </div>
          <div className="row" style={{ marginTop: "1rem" }}>
            <button className="btn primary" onClick={handleExport} disabled={exporting}>
              {exporting ? "Exporting..." : "Download export"}
            </button>
            {exportStatus && <span className="help">{exportStatus}</span>}
          </div>
        </section>
      )}

      {activeTab === "retention" && (
        <section className="card">
          <h2 className="section-title">Retention evidence</h2>
          <p className="subtle">
            Shows executed retention runs, deletion counts, and cutoff dates.
          </p>
          <div className="row" style={{ marginBottom: "1rem" }}>
            <button className="btn secondary" onClick={loadRetentionRuns} disabled={runsLoading}>
              {runsLoading ? "Refreshing..." : "Refresh runs"}
            </button>
            {runsError && <span className="help" style={{ color: "var(--danger)" }}>{runsError}</span>}
          </div>
          {runsLoading && <p className="subtle">Loading retention evidence...</p>}
          {!runsLoading && !runsError && retentionRuns.length === 0 && (
            <p className="subtle">No retention runs recorded yet.</p>
          )}
          {retentionRuns.length > 0 && (
            <table className="table">
              <thead>
                <tr>
                  <th>Run</th>
                  <th>Status</th>
                  <th>Started</th>
                  <th>Finished</th>
                  <th>Event cutoff</th>
                  <th>Raw IP cutoff</th>
                  <th>Deleted</th>
                  <th>Scrubbed IPs</th>
                </tr>
              </thead>
              <tbody>
                {retentionRuns.map((run) => {
                  const deletedTotal =
                    (run.behaviour_events_deleted || 0) +
                    (run.security_events_deleted || 0);
                  const scrubbedTotal =
                    (run.alerts_raw_ip_scrubbed || 0) +
                    (run.events_raw_ip_scrubbed || 0) +
                    (run.audit_logs_raw_ip_scrubbed || 0) +
                    (run.security_events_raw_ip_scrubbed || 0);
                  return (
                    <tr key={run.id}>
                      <td>#{run.id}</td>
                      <td>{run.status}</td>
                      <td>{formatDateTime(run.started_at)}</td>
                      <td>{formatDateTime(run.finished_at)}</td>
                      <td>{formatDateTime(run.event_cutoff)}</td>
                      <td>{formatDateTime(run.raw_ip_cutoff)}</td>
                      <td>{deletedTotal.toLocaleString()}</td>
                      <td>{scrubbedTotal.toLocaleString()}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </section>
      )}
    </div>
  );
}
