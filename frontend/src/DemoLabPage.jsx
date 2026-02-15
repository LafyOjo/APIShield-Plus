import { useCallback, useEffect, useMemo, useState } from "react";
import { ACTIVE_TENANT_KEY, apiFetch } from "./api";

const PREVIEW_MAX_CHARS = 1600;

const RANGE_OPTIONS = [
  { label: "Last 1 hour", value: 1 },
  { label: "Last 6 hours", value: 6 },
  { label: "Last 24 hours", value: 24 },
  { label: "Last 72 hours", value: 72 },
];

function buildRange(hours) {
  const to = new Date();
  const from = new Date(to.getTime() - hours * 60 * 60 * 1000);
  return {
    fromIso: from.toISOString(),
    toIso: to.toISOString(),
  };
}

function buildPreview(payload) {
  if (payload == null) return "(empty)";
  const raw = typeof payload === "string" ? payload : JSON.stringify(payload, null, 2);
  if (raw.length <= PREVIEW_MAX_CHARS) return raw;
  return `${raw.slice(0, PREVIEW_MAX_CHARS)}\n...truncated`;
}

function buildSummary(payload) {
  if (Array.isArray(payload)) {
    return `${payload.length} item${payload.length === 1 ? "" : "s"}`;
  }
  if (payload && typeof payload === "object") {
    if (Array.isArray(payload.items)) {
      return `${payload.items.length} item${payload.items.length === 1 ? "" : "s"}`;
    }
    if (payload.summary && typeof payload.summary === "object") {
      return "summary payload";
    }
    return `${Object.keys(payload).length} field${Object.keys(payload).length === 1 ? "" : "s"}`;
  }
  return String(payload);
}

function parseResponsePayload(response) {
  if (response.status === 204) {
    return Promise.resolve(null);
  }
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  return response.text();
}

function endpointLabelClass(result) {
  if (!result) return "badge";
  if (result.running) return "badge";
  return result.ok ? "badge demo-status-ok" : "badge demo-status-fail";
}

function DemoLabPage({ onNavigate }) {
  const [windowHours, setWindowHours] = useState(24);
  const [results, setResults] = useState({});
  const [lastRunAt, setLastRunAt] = useState(null);
  const [runningAll, setRunningAll] = useState(false);
  const [seedStatus, setSeedStatus] = useState("");

  const activeTenantId = localStorage.getItem(ACTIVE_TENANT_KEY) || "(not selected)";
  const { fromIso, toIso } = useMemo(() => buildRange(windowHours), [windowHours]);

  const checks = useMemo(() => {
    const from = encodeURIComponent(fromIso);
    const to = encodeURIComponent(toIso);
    return [
      {
        id: "me",
        title: "Session and tenant context",
        path: "/api/v1/me",
        note: "Auth and membership payload used by bootstrapping.",
      },
      {
        id: "tenants",
        title: "Tenant list",
        path: "/api/v1/tenants",
        note: "All tenants linked to the logged-in user.",
      },
      {
        id: "map_summary",
        title: "Map summary",
        path: `/api/v1/map/summary?from=${from}&to=${to}`,
        note: "Geo aggregate points for current range.",
      },
      {
        id: "trust",
        title: "Trust snapshots",
        path: `/api/v1/trust/snapshots?from=${from}&to=${to}&limit=50`,
        note: "Hourly trust scoring buckets.",
      },
      {
        id: "leaks",
        title: "Revenue leaks",
        path: `/api/v1/revenue/leaks?from=${from}&to=${to}&limit=10`,
        note: "Leak leaderboard (plan-gated on lower tiers).",
      },
      {
        id: "portfolio",
        title: "Portfolio summary",
        path: `/api/v1/portfolio/summary?from=${from}&to=${to}`,
        note: "Multi-site rollup (plan-gated).",
      },
      {
        id: "admin_perf",
        title: "Admin perf ring buffer",
        path: "/api/v1/admin/perf/requests",
        note: "Last 200 profiled requests (platform admin only).",
      },
      {
        id: "admin_queue",
        title: "Admin queue stats",
        path: "/api/v1/admin/queue/stats",
        note: "Queue depth and retry telemetry (platform admin only).",
      },
    ];
  }, [fromIso, toIso]);

  const runCheck = useCallback(async (check) => {
    setResults((prev) => ({
      ...prev,
      [check.id]: {
        ...prev[check.id],
        running: true,
      },
    }));

    const start = performance.now();
    try {
      const response = await apiFetch(check.path, { skipReauth: true });
      const payload = await parseResponsePayload(response);
      const durationMs = performance.now() - start;
      const ok = response.ok;
      const detail = payload && typeof payload === "object" ? payload.detail : null;

      setResults((prev) => ({
        ...prev,
        [check.id]: {
          running: false,
          ok,
          status: response.status,
          durationMs,
          summary: buildSummary(payload),
          preview: buildPreview(payload),
          detail: typeof detail === "string" ? detail : "",
          fetchedAt: new Date().toISOString(),
        },
      }));
    } catch (error) {
      const durationMs = performance.now() - start;
      setResults((prev) => ({
        ...prev,
        [check.id]: {
          running: false,
          ok: false,
          status: null,
          durationMs,
          summary: "request failed",
          preview: String(error),
          detail: String(error),
          fetchedAt: new Date().toISOString(),
        },
      }));
    }
  }, []);

  const runAllChecks = useCallback(async () => {
    setRunningAll(true);
    for (const check of checks) {
      await runCheck(check);
    }
    setLastRunAt(new Date().toISOString());
    setRunningAll(false);
  }, [checks, runCheck]);

  useEffect(() => {
    void runAllChecks();
  }, [runAllChecks]);

  const seedDemoData = useCallback(async () => {
    setSeedStatus("Seeding demo data...");
    try {
      const response = await apiFetch("/api/v1/demo/seed", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ force: false }),
      });
      const payload = await parseResponsePayload(response);
      if (!response.ok) {
        const detail = payload && typeof payload === "object" ? payload.detail : "Failed to seed demo data";
        setSeedStatus(typeof detail === "string" ? detail : "Failed to seed demo data");
        return;
      }
      const counts = payload && typeof payload === "object" ? payload.counts : null;
      const countText = counts && typeof counts === "object" ? JSON.stringify(counts) : "ready";
      setSeedStatus(`Demo data seeded: ${countText}`);
      await runAllChecks();
    } catch (error) {
      setSeedStatus(`Seed failed: ${String(error)}`);
    }
  }, [runAllChecks]);

  const openRoute = (path) => {
    if (typeof onNavigate === "function") {
      onNavigate(path);
      return;
    }
    window.history.pushState({}, "", path);
    window.dispatchEvent(new PopStateEvent("popstate"));
  };

  return (
    <section className="card demo-lab-page">
      <div className="demo-lab-header">
        <div>
          <h2 className="section-title">Demo Lab</h2>
          <p className="muted">
            Live endpoint smoke dashboard for the current session and tenant context.
          </p>
        </div>
        <span className="badge">Tenant: {activeTenantId}</span>
      </div>

      <div className="demo-lab-controls">
        <label htmlFor="demo-window-hours">Time window</label>
        <select
          id="demo-window-hours"
          value={windowHours}
          onChange={(event) => setWindowHours(Number(event.target.value) || 24)}
        >
          {RANGE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <button className="btn secondary" onClick={runAllChecks} disabled={runningAll}>
          {runningAll ? "Running checks..." : "Run checks"}
        </button>
        <button className="btn secondary" onClick={seedDemoData}>
          Seed demo data
        </button>
        <button className="btn secondary" onClick={() => openRoute("/dashboard/security/map")}>
          Open map
        </button>
        <button className="btn secondary" onClick={() => openRoute("/dashboard/revenue-integrity/incidents")}>
          Open incidents
        </button>
      </div>

      {seedStatus ? <p className="muted">{seedStatus}</p> : null}
      <p className="muted small">
        Range: {fromIso} to {toIso}
        {lastRunAt ? ` | Last run: ${new Date(lastRunAt).toLocaleString()}` : ""}
      </p>

      <div className="demo-lab-table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Check</th>
              <th>Status</th>
              <th>Duration</th>
              <th>Summary</th>
            </tr>
          </thead>
          <tbody>
            {checks.map((check) => {
              const result = results[check.id];
              const durationText =
                result && typeof result.durationMs === "number"
                  ? `${result.durationMs.toFixed(1)} ms`
                  : "-";
              const summaryText =
                result && typeof result.summary === "string"
                  ? result.summary
                  : result?.running
                  ? "running"
                  : "waiting";
              const badgeText = result
                ? result.running
                  ? "RUNNING"
                  : result.ok
                  ? "OK"
                  : "ERROR"
                : "IDLE";
              return (
                <tr key={check.id}>
                  <td>
                    <div className="demo-lab-check-title">{check.title}</div>
                    <div className="muted small">{check.path}</div>
                    <div className="muted small">{check.note}</div>
                    {result?.detail ? <div className="error small">{result.detail}</div> : null}
                    {result?.preview ? (
                      <details className="demo-lab-preview">
                        <summary>Response preview</summary>
                        <pre>{result.preview}</pre>
                      </details>
                    ) : null}
                  </td>
                  <td>
                    <span className={endpointLabelClass(result)}>
                      {badgeText}
                      {result?.status ? ` (${result.status})` : ""}
                    </span>
                  </td>
                  <td>{durationText}</td>
                  <td>{summaryText}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default DemoLabPage;
