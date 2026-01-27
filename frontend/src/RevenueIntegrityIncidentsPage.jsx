import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch, ACTIVE_TENANT_KEY } from "./api";
import DemoDataToggle from "./DemoDataToggle";
import { useDemoData } from "./useDemoData";

const TIME_RANGES = [
  { value: "24h", label: "Last 24 hours", days: 1 },
  { value: "7d", label: "Last 7 days", days: 7 },
  { value: "30d", label: "Last 30 days", days: 30 },
];

const STATUS_OPTIONS = [
  { value: "", label: "Any status" },
  { value: "open", label: "Open" },
  { value: "investigating", label: "Investigating" },
  { value: "mitigated", label: "Mitigated" },
  { value: "resolved", label: "Resolved" },
];

const CATEGORY_OPTIONS = [
  { value: "", label: "Any category" },
  { value: "login", label: "Login" },
  { value: "threat", label: "Threat" },
  { value: "integrity", label: "Integrity" },
  { value: "bot", label: "Bot" },
  { value: "anomaly", label: "Anomaly" },
  { value: "mixed", label: "Mixed" },
];

const SEVERITY_OPTIONS = [
  { value: "", label: "Any severity" },
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
  { value: "critical", label: "Critical" },
];

const DAY_MS = 24 * 60 * 60 * 1000;
const CUSTOM_RANGE_VALUE = "custom";
const TIME_RANGE_TOLERANCE_MS = 15 * 60 * 1000;

const isValidDate = (value) =>
  value instanceof Date && !Number.isNaN(value.getTime());

const parseDateParam = (value) => {
  if (!value) return null;
  const parsed = new Date(value);
  return isValidDate(parsed) ? parsed : null;
};

const buildTimeWindow = (days, now = new Date()) => {
  const to = new Date(now);
  const from = new Date(now.getTime() - days * DAY_MS);
  return { from, to };
};

const ensureTimeWindow = ({ from, to, now, fallbackDays }) => {
  const safeNow = now ? new Date(now) : new Date();
  let nextTo = isValidDate(to) ? to : null;
  if (!nextTo || nextTo > safeNow) {
    nextTo = new Date(safeNow);
  }
  let nextFrom = isValidDate(from) ? from : null;
  if (!nextFrom || nextFrom > nextTo) {
    nextFrom = new Date(nextTo.getTime() - fallbackDays * DAY_MS);
  }
  return { from: nextFrom, to: nextTo };
};

const resolveRangeValue = (from, to) => {
  if (!isValidDate(from) || !isValidDate(to)) return TIME_RANGES[0].value;
  const diffMs = to.getTime() - from.getTime();
  if (diffMs <= 0) return TIME_RANGES[0].value;
  const match = TIME_RANGES.find(
    (option) => Math.abs(option.days * DAY_MS - diffMs) <= TIME_RANGE_TOLERANCE_MS
  );
  return match ? match.value : CUSTOM_RANGE_VALUE;
};

const parseIdParam = (value) => {
  if (!value) return "";
  return /^\d+$/.test(value) ? value : "";
};

const parseOptionParam = (value, options, fallback = "") => {
  if (!value) return fallback;
  const match = options.find((option) => option.value === value);
  return match ? match.value : fallback;
};

const formatDateTime = (value) => {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--";
  return date.toLocaleString();
};

const formatCurrency = (value) => {
  if (value == null || Number.isNaN(value)) return "--";
  return value.toLocaleString(undefined, { style: "currency", currency: "USD" });
};

const formatConfidence = (value) => {
  if (value == null || Number.isNaN(value)) return "--";
  return `${Math.round(value * 100)}%`;
};

const getInitialFilters = () => {
  const params = new URLSearchParams(window.location.search);
  const fromParam = parseDateParam(params.get("from"));
  const toParam = parseDateParam(params.get("to"));
  const { from, to } = ensureTimeWindow({
    from: fromParam,
    to: toParam,
    now: new Date(),
    fallbackDays: TIME_RANGES[0].days,
  });
  return {
    from,
    to,
    websiteId: parseIdParam(params.get("website_id")),
    status: parseOptionParam(params.get("status"), STATUS_OPTIONS),
    category: parseOptionParam(params.get("category"), CATEGORY_OPTIONS),
    severity: parseOptionParam(params.get("severity"), SEVERITY_OPTIONS),
  };
};

export default function RevenueIntegrityIncidentsPage() {
  const initialFilters = useMemo(() => getInitialFilters(), []);
  const [tenants, setTenants] = useState([]);
  const [activeTenant, setActiveTenant] = useState(
    localStorage.getItem(ACTIVE_TENANT_KEY) || ""
  );
  const [websites, setWebsites] = useState([]);
  const [websiteId, setWebsiteId] = useState(initialFilters.websiteId);
  const [status, setStatus] = useState(initialFilters.status);
  const [category, setCategory] = useState(initialFilters.category);
  const [severity, setSeverity] = useState(initialFilters.severity);
  const [fromTs, setFromTs] = useState(initialFilters.from);
  const [toTs, setToTs] = useState(initialFilters.to);
  const [impactEnabled, setImpactEnabled] = useState(true);
  const [incidents, setIncidents] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const { enabled: includeDemo, setEnabled: setIncludeDemo } = useDemoData();
  const [debouncedFilters, setDebouncedFilters] = useState({
    activeTenant,
    websiteId,
    status,
    category,
    severity,
    from: fromTs,
    to: toTs,
    includeDemo,
  });

  const rangeValue = useMemo(() => resolveRangeValue(fromTs, toTs), [fromTs, toTs]);
  const rangeOptions = useMemo(() => {
    if (rangeValue !== CUSTOM_RANGE_VALUE) return TIME_RANGES;
    return [
      ...TIME_RANGES,
      { value: CUSTOM_RANGE_VALUE, label: "Custom range", days: null, disabled: true },
    ];
  }, [rangeValue]);

  const updateTimeWindow = useCallback((days) => {
    const nextWindow = buildTimeWindow(days, new Date());
    setFromTs(nextWindow.from);
    setToTs(nextWindow.to);
  }, []);

  const navigateTo = useCallback((path) => {
    if (!path) return;
    window.history.pushState({}, "", path);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, []);

  useEffect(() => {
    let mounted = true;
    async function loadTenants() {
      try {
        const resp = await apiFetch("/api/v1/tenants");
        if (!resp.ok) {
          throw new Error("Unable to load tenants");
        }
        const data = await resp.json();
        if (!mounted) return;
        setTenants(data);
        if (!activeTenant && data.length) {
          const first = data[0];
          setActiveTenant(first.slug);
          localStorage.setItem(ACTIVE_TENANT_KEY, String(first.slug));
        }
      } catch (err) {
        if (!mounted) return;
        setError(err.message || "Unable to load tenants");
      }
    }
    loadTenants();
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (!activeTenant) {
      localStorage.removeItem(ACTIVE_TENANT_KEY);
      setWebsites([]);
      setWebsiteId("");
      return;
    }
    localStorage.setItem(ACTIVE_TENANT_KEY, activeTenant);
    let mounted = true;
    async function loadWebsites() {
      try {
        const resp = await apiFetch("/api/v1/websites");
        if (!resp.ok) {
          throw new Error("Unable to load websites");
        }
        const data = await resp.json();
        if (!mounted) return;
        setWebsites(data);
      } catch (err) {
        if (!mounted) return;
        setWebsites([]);
        setWebsiteId("");
      }
    }
    loadWebsites();
    return () => {
      mounted = false;
    };
  }, [activeTenant]);

  useEffect(() => {
    if (!activeTenant) return;
    let mounted = true;
    async function loadEntitlements() {
      try {
        const resp = await apiFetch("/api/v1/me", { skipReauth: true });
        if (!resp.ok) {
          throw new Error("Unable to load entitlements");
        }
        const data = await resp.json();
        if (!mounted) return;
        const entitlements = data?.entitlements || {};
        const features = entitlements.features || {};
        setImpactEnabled(Boolean(features.prescriptions));
      } catch (err) {
        if (!mounted) return;
        setImpactEnabled(true);
      }
    }
    loadEntitlements();
    return () => {
      mounted = false;
    };
  }, [activeTenant]);

  useEffect(() => {
    const handle = setTimeout(() => {
      setDebouncedFilters({
        activeTenant,
        websiteId,
        status,
        category,
        severity,
        from: fromTs,
        to: toTs,
        includeDemo,
      });
    }, 250);
    return () => clearTimeout(handle);
  }, [activeTenant, websiteId, status, category, severity, fromTs, toTs, includeDemo]);

  useEffect(() => {
    if (!isValidDate(fromTs) || !isValidDate(toTs)) return;
    const params = new URLSearchParams();
    params.set("from", fromTs.toISOString());
    params.set("to", toTs.toISOString());
    if (websiteId) params.set("website_id", websiteId);
    if (status) params.set("status", status);
    if (category) params.set("category", category);
    if (severity) params.set("severity", severity);
    if (includeDemo) params.set("demo", "1");
    const nextUrl = `${window.location.pathname}?${params.toString()}${window.location.hash || ""}`;
    window.history.replaceState({}, "", nextUrl);
  }, [fromTs, toTs, websiteId, status, category, severity, includeDemo]);

  useEffect(() => {
    if (!debouncedFilters.activeTenant) return;
    let mounted = true;
    async function loadIncidents() {
      setLoading(true);
      setError("");
      try {
        const params = new URLSearchParams();
        params.set("from", debouncedFilters.from.toISOString());
        params.set("to", debouncedFilters.to.toISOString());
        if (debouncedFilters.websiteId) {
          params.set("website_id", debouncedFilters.websiteId);
        }
        if (debouncedFilters.status) params.set("status", debouncedFilters.status);
        if (debouncedFilters.category) params.set("category", debouncedFilters.category);
        if (debouncedFilters.severity) params.set("severity", debouncedFilters.severity);
        if (debouncedFilters.includeDemo) params.set("include_demo", "true");
        const resp = await apiFetch(`/api/v1/incidents?${params.toString()}`);
        if (!resp.ok) {
          throw new Error("Unable to load incidents");
        }
        const data = await resp.json();
        if (!mounted) return;
        setIncidents(Array.isArray(data) ? data : []);
      } catch (err) {
        if (!mounted) return;
        setIncidents([]);
        setError(err.message || "Unable to load incidents");
      } finally {
        if (mounted) setLoading(false);
      }
    }
    loadIncidents();
    return () => {
      mounted = false;
    };
  }, [debouncedFilters]);

  return (
    <div className="stack">
      <section className="card incidents-header">
        <div>
          <h2 className="section-title">Revenue Integrity Incidents</h2>
          <p className="subtle">
            Track conversion-impacting incidents, costs, and recommended actions.
          </p>
          <div className="row revenue-nav">
            <button className="btn secondary nav-tab active">Incidents</button>
            <button
              className="btn secondary nav-tab"
              onClick={() => navigateTo("/dashboard/revenue-integrity/leaks")}
            >
              Leak Heatmap
            </button>
          </div>
        </div>
        <div className="incidents-tenant">
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
        <div className="controls-grid incidents-filters">
          <div className="field">
            <label className="label">Time range</label>
            <select
              className="select"
              value={rangeValue}
              onChange={(e) => {
                const selected = TIME_RANGES.find((option) => option.value === e.target.value);
                if (selected) updateTimeWindow(selected.days);
              }}
            >
              {rangeOptions.map((option) => (
                <option
                  key={option.value}
                  value={option.value}
                  disabled={option.disabled}
                >
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label className="label">Website</label>
            <select
              className="select"
              value={websiteId}
              onChange={(e) => setWebsiteId(e.target.value)}
            >
              <option value="">All websites</option>
              {websites.map((site) => (
                <option key={site.id} value={site.id}>
                  {site.display_name || site.domain}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label className="label">Status</label>
            <select
              className="select"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              {STATUS_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label className="label">Category</label>
            <select
              className="select"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            >
              {CATEGORY_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label className="label">Severity</label>
            <select
              className="select"
              value={severity}
              onChange={(e) => setSeverity(e.target.value)}
            >
              {SEVERITY_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label className="label">Demo data</label>
            <DemoDataToggle
              enabled={includeDemo}
              onToggle={() => setIncludeDemo((prev) => !prev)}
            />
          </div>
        </div>
      </section>

      <section className="card">
        <div className="incidents-table-header">
          <div>
            <h3 className="section-title">Incidents</h3>
            <div className="subtle">
              {incidents.length ? `${incidents.length} incidents` : "No incidents yet."}
            </div>
          </div>
        </div>
        {loading && <p className="subtle">Loading incidents...</p>}
        {error && <p className="error-text">{error}</p>}
        {!loading && !error && incidents.length === 0 && (
          <p className="subtle">
            No incidents match this time window. Try expanding your filters.
          </p>
        )}
        {!loading && !error && incidents.length > 0 && (
          <table className="table incidents-table">
            <thead>
              <tr>
                <th>Incident</th>
                <th>Category</th>
                <th>Severity</th>
                <th>
                  Est. loss{" "}
                  {!impactEnabled && (
                    <span className="badge pro" title="Upgrade to unlock impact estimates.">
                      Pro
                    </span>
                  )}
                </th>
                <th>Confidence</th>
                <th>Last seen</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {incidents.map((incident) => {
                const impact = incident.impact_summary || {};
                return (
                  <tr key={incident.id}>
                    <td>
                      <div className="incident-title">{incident.title}</div>
                      <div className="subtle">#{incident.id}</div>
                    </td>
                    <td>{incident.category || "--"}</td>
                    <td>{incident.severity || "--"}</td>
                    <td>
                      {impactEnabled
                        ? formatCurrency(impact.estimated_lost_revenue)
                        : "Upgrade"}
                    </td>
                    <td>
                      {impactEnabled
                        ? formatConfidence(impact.confidence)
                        : "--"}
                    </td>
                    <td>{formatDateTime(incident.last_seen_at)}</td>
                    <td>
                      <span className={`status-chip ${incident.status || "open"}`}>
                        {incident.status || "open"}
                      </span>
                    </td>
                    <td>
                      <button
                        className="btn secondary small"
                        onClick={() =>
                          navigateTo(
                            includeDemo
                              ? `/dashboard/revenue-integrity/incidents/${incident.id}?demo=1`
                              : `/dashboard/revenue-integrity/incidents/${incident.id}`
                          )
                        }
                      >
                        View
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
