import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch, ACTIVE_TENANT_KEY } from "./api";
import DemoDataToggle from "./DemoDataToggle";
import { useDemoData } from "./useDemoData";

const TIME_RANGES = [
  { value: "24h", label: "Last 24 hours", days: 1 },
  { value: "7d", label: "Last 7 days", days: 7 },
  { value: "30d", label: "Last 30 days", days: 30 },
];

const CATEGORY_TABS = [
  { value: "login", label: "Logins" },
  { value: "threat", label: "Threats" },
  { value: "integrity", label: "Integrity" },
  { value: "bot", label: "Bots" },
];

const CATEGORY_LABELS = CATEGORY_TABS.reduce((acc, item) => {
  acc[item.value] = item.label;
  return acc;
}, {});

const SEVERITY_OPTIONS = [
  { value: "", label: "Any severity" },
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
  { value: "critical", label: "Critical" },
];

const GRANULARITY_LEVELS = { country: 0, city: 1, asn: 2 };

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

const clampTimeWindow = ({ from, to, now, maxDays }) => {
  if (!maxDays) {
    return { from, to, clamped: false };
  }
  const safeNow = now ? new Date(now) : new Date();
  const maxStart = new Date(safeNow.getTime() - maxDays * DAY_MS);
  let nextFrom = from;
  let nextTo = to;
  let clamped = false;

  if (nextTo > safeNow) {
    nextTo = new Date(safeNow);
    clamped = true;
  }
  if (nextFrom < maxStart) {
    nextFrom = new Date(maxStart);
    clamped = true;
  }
  if (nextTo < maxStart) {
    nextTo = new Date(safeNow);
    clamped = true;
  }
  if (nextFrom > nextTo) {
    nextFrom = new Date(maxStart);
    clamped = true;
  }
  return { from: nextFrom, to: nextTo, clamped };
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

const parseCategoryParam = (value) => {
  if (!value) return CATEGORY_TABS[0].value;
  const match = CATEGORY_TABS.find((option) => option.value === value);
  return match ? match.value : CATEGORY_TABS[0].value;
};

const parseSeverityParam = (value) => {
  if (!value) return "";
  const match = SEVERITY_OPTIONS.find((option) => option.value === value);
  return match ? match.value : "";
};

const parseTextParam = (value) => (value ? String(value).trim() : "");

const parseCountryParam = (value) => {
  if (!value) return "";
  const normalized = String(value).trim().toUpperCase();
  return /^[A-Z]{2}$/.test(normalized) ? normalized : "";
};

const isSameInstant = (left, right) =>
  isValidDate(left) && isValidDate(right) && left.getTime() === right.getTime();

const formatCategoryLabel = (value) =>
  CATEGORY_LABELS[value] || value || "Unknown";

const formatEventType = (value) => {
  if (!value) return "";
  return value.replace(/_/g, " ");
};

const formatDateTime = (value) => {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString();
};

const maskHash = (value) => {
  if (!value) return "";
  if (value.length <= 12) return value;
  return `${value.slice(0, 6)}...${value.slice(-4)}`;
};

const formatLocation = (item) => {
  if (!item) return "";
  if (item.city || item.region) {
    return `${item.city || "Unknown"}, ${item.region || ""}`.replace(/,\s*$/, "");
  }
  return item.country_code || "";
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
    envId: parseIdParam(params.get("env_id")),
    category: parseCategoryParam(params.get("category")),
    severity: parseSeverityParam(params.get("severity")),
    ipHash: parseTextParam(params.get("ip_hash")),
    countryCode: parseCountryParam(params.get("country_code")),
  };
};

export default function SecurityEventsPage() {
  const initialFilters = useMemo(() => getInitialFilters(), []);
  const [tenants, setTenants] = useState([]);
  const [activeTenant, setActiveTenant] = useState(
    localStorage.getItem(ACTIVE_TENANT_KEY) || ""
  );
  const [websites, setWebsites] = useState([]);
  const [environments, setEnvironments] = useState([]);
  const [websiteId, setWebsiteId] = useState(initialFilters.websiteId);
  const [envId, setEnvId] = useState(initialFilters.envId);
  const [category, setCategory] = useState(initialFilters.category);
  const [severity, setSeverity] = useState(initialFilters.severity);
  const [fromTs, setFromTs] = useState(initialFilters.from);
  const [toTs, setToTs] = useState(initialFilters.to);
  const [ipHash, setIpHash] = useState(initialFilters.ipHash);
  const [countryCode, setCountryCode] = useState(initialFilters.countryCode);
  const [geoFeatureEnabled, setGeoFeatureEnabled] = useState(null);
  const [geoGranularity, setGeoGranularity] = useState(null);
  const [geoHistoryDays, setGeoHistoryDays] = useState(null);
  const [timeClampNotice, setTimeClampNotice] = useState("");
  const [events, setEvents] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const { enabled: includeDemo, setEnabled: setIncludeDemo } = useDemoData();
  const [debouncedFilters, setDebouncedFilters] = useState({
    activeTenant,
    websiteId,
    envId,
    category,
    severity,
    from: fromTs,
    to: toTs,
    ipHash,
    countryCode,
    includeDemo,
  });

  const geoEnabled = geoFeatureEnabled !== false;
  const resolvedGranularity = geoGranularity || "city";
  const granularityRank =
    GRANULARITY_LEVELS[resolvedGranularity] ?? GRANULARITY_LEVELS.city;
  const hasAsnGranularity = geoEnabled && granularityRank >= GRANULARITY_LEVELS.asn;
  const hasHistoryLimit = useMemo(
    () => Boolean(geoHistoryDays && TIME_RANGES.some((option) => option.days > geoHistoryDays)),
    [geoHistoryDays]
  );

  const rangeValue = useMemo(() => resolveRangeValue(fromTs, toTs), [fromTs, toTs]);
  const rangeOptions = useMemo(() => {
    const options = TIME_RANGES.map((option) => {
      const isLimited = geoHistoryDays ? option.days > geoHistoryDays : false;
      const label = isLimited ? `${option.label} (Pro)` : option.label;
      return { ...option, label, disabled: isLimited };
    });
    if (rangeValue !== CUSTOM_RANGE_VALUE) return options;
    return [
      ...options,
      { value: CUSTOM_RANGE_VALUE, label: "Custom range", days: null, disabled: true },
    ];
  }, [rangeValue, geoHistoryDays]);

  const updateTimeWindow = useCallback(
    (nextFrom, nextTo) => {
      const now = new Date();
      const normalized = ensureTimeWindow({
        from: nextFrom,
        to: nextTo,
        now,
        fallbackDays: TIME_RANGES[0].days,
      });
      let finalFrom = normalized.from;
      let finalTo = normalized.to;
      let clamped = false;
      if (geoHistoryDays) {
        const clampResult = clampTimeWindow({
          from: normalized.from,
          to: normalized.to,
          now,
          maxDays: geoHistoryDays,
        });
        finalFrom = clampResult.from;
        finalTo = clampResult.to;
        clamped = clampResult.clamped;
      }
      if (clamped) {
        setTimeClampNotice(
          `Time range limited to last ${geoHistoryDays} days for your plan.`
        );
      } else {
        setTimeClampNotice("");
      }
      setFromTs((prev) => (isSameInstant(prev, finalFrom) ? prev : finalFrom));
      setToTs((prev) => (isSameInstant(prev, finalTo) ? prev : finalTo));
    },
    [geoHistoryDays]
  );

  const handleRangeChange = (event) => {
    const selected = TIME_RANGES.find((option) => option.value === event.target.value);
    if (!selected) return;
    if (geoHistoryDays && selected.days > geoHistoryDays) return;
    const nextWindow = buildTimeWindow(selected.days, new Date());
    updateTimeWindow(nextWindow.from, nextWindow.to);
  };

  const navigateTo = useCallback((path) => {
    if (!path) return;
    window.history.pushState({}, "", path);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, []);

  const timeWindow = useMemo(() => {
    if (!isValidDate(debouncedFilters.from) || !isValidDate(debouncedFilters.to)) {
      return buildTimeWindow(TIME_RANGES[0].days, new Date());
    }
    return { from: debouncedFilters.from, to: debouncedFilters.to };
  }, [debouncedFilters.from, debouncedFilters.to]);

  const buildMapLink = useCallback(
    (eventRow) => {
      if (!isValidDate(timeWindow.from) || !isValidDate(timeWindow.to)) {
        return "/dashboard/security/map";
      }
      const params = new URLSearchParams();
      params.set("from", timeWindow.from.toISOString());
      params.set("to", timeWindow.to.toISOString());
      if (websiteId) params.set("website_id", websiteId);
      if (envId) params.set("env_id", envId);
      if (category) params.set("category", category);
      if (severity) params.set("severity", severity);
      if (eventRow?.latitude != null && eventRow?.longitude != null) {
        params.set("lat", String(eventRow.latitude));
        params.set("lon", String(eventRow.longitude));
        params.set("radius_km", "80");
      } else if (eventRow?.country_code) {
        params.set("country_code", eventRow.country_code);
      }
      return `/dashboard/security/map?${params.toString()}`;
    },
    [category, envId, severity, timeWindow.from, timeWindow.to, websiteId]
  );

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
      setEnvironments([]);
      setWebsiteId("");
      setEnvId("");
      setGeoFeatureEnabled(null);
      setGeoGranularity(null);
      setGeoHistoryDays(null);
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
        setEnvironments([]);
        setWebsiteId("");
        setEnvId("");
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
        const limits = entitlements.limits || {};
        const features = entitlements.features || {};
        const limitValue = Number(limits.geo_history_days);
        const featureEnabled =
          typeof features.geo_map === "boolean" ? features.geo_map : null;
        const granularityValue = String(limits.geo_granularity || "").toLowerCase();
        const normalizedGranularity =
          GRANULARITY_LEVELS[granularityValue] != null ? granularityValue : null;
        const effectiveHistory =
          featureEnabled === false
            ? 1
            : Number.isFinite(limitValue) && limitValue > 0
              ? limitValue
              : null;
        setGeoFeatureEnabled(featureEnabled);
        setGeoGranularity(normalizedGranularity);
        setGeoHistoryDays(effectiveHistory);
      } catch (err) {
        if (!mounted) return;
        setGeoFeatureEnabled(null);
        setGeoGranularity(null);
        setGeoHistoryDays(null);
      }
    }
    loadEntitlements();
    return () => {
      mounted = false;
    };
  }, [activeTenant]);

  useEffect(() => {
    if (!geoHistoryDays) {
      setTimeClampNotice("");
      return;
    }
    updateTimeWindow(fromTs, toTs);
  }, [geoHistoryDays, updateTimeWindow, fromTs, toTs]);

  useEffect(() => {
    if (!activeTenant || !websiteId) {
      setEnvironments([]);
      setEnvId("");
      return;
    }
    let mounted = true;
    async function loadEnvironments() {
      try {
        const resp = await apiFetch(`/api/v1/websites/${websiteId}/install`);
        if (!resp.ok) {
          throw new Error("Unable to load environments");
        }
        const data = await resp.json();
        if (!mounted) return;
        setEnvironments(data.environments || []);
      } catch (err) {
        if (!mounted) return;
        setEnvironments([]);
      }
    }
    loadEnvironments();
    return () => {
      mounted = false;
    };
  }, [activeTenant, websiteId]);

  useEffect(() => {
    if (!websiteId) return;
    if (!websites.length) return;
    const exists = websites.some((site) => String(site.id) === websiteId);
    if (!exists) {
      setWebsiteId("");
    }
  }, [websiteId, websites]);

  useEffect(() => {
    if (!envId) return;
    if (!environments.length) return;
    const exists = environments.some((env) => String(env.id) === envId);
    if (!exists) {
      setEnvId("");
    }
  }, [envId, environments]);

  useEffect(() => {
    const handle = setTimeout(() => {
      setDebouncedFilters({
        activeTenant,
        websiteId,
        envId,
        category,
        severity,
        from: fromTs,
        to: toTs,
        ipHash,
        countryCode,
        includeDemo,
      });
    }, 250);
    return () => clearTimeout(handle);
  }, [activeTenant, websiteId, envId, category, severity, fromTs, toTs, ipHash, countryCode, includeDemo]);

  useEffect(() => {
    if (!isValidDate(fromTs) || !isValidDate(toTs)) return;
    const params = new URLSearchParams();
    params.set("from", fromTs.toISOString());
    params.set("to", toTs.toISOString());
    if (websiteId) params.set("website_id", websiteId);
    if (envId) params.set("env_id", envId);
    if (category) params.set("category", category);
    if (severity) params.set("severity", severity);
    if (ipHash) params.set("ip_hash", ipHash);
    if (countryCode) params.set("country_code", countryCode);
    if (includeDemo) params.set("demo", "1");
    const nextUrl = `${window.location.pathname}?${params.toString()}${window.location.hash || ""}`;
    window.history.replaceState({}, "", nextUrl);
  }, [fromTs, toTs, websiteId, envId, category, severity, ipHash, countryCode, includeDemo]);

  useEffect(() => {
    if (!debouncedFilters.activeTenant) return;
    let mounted = true;
    async function loadEvents() {
      setLoading(true);
      setError("");
      try {
        const params = new URLSearchParams();
        params.set("from", timeWindow.from.toISOString());
        params.set("to", timeWindow.to.toISOString());
        if (debouncedFilters.websiteId) {
          params.set("website_id", debouncedFilters.websiteId);
        }
        if (debouncedFilters.envId) params.set("env_id", debouncedFilters.envId);
        if (debouncedFilters.category) params.set("category", debouncedFilters.category);
        if (debouncedFilters.severity) params.set("severity", debouncedFilters.severity);
        if (debouncedFilters.ipHash) params.set("ip_hash", debouncedFilters.ipHash);
        if (debouncedFilters.countryCode) {
          params.set("country_code", debouncedFilters.countryCode);
        }
        if (debouncedFilters.includeDemo) {
          params.set("include_demo", "true");
        }
        params.set("page_size", "100");
        const resp = await apiFetch(`/api/v1/security/events?${params.toString()}`);
        if (!resp.ok) {
          throw new Error("Unable to load security events");
        }
        const data = await resp.json();
        if (!mounted) return;
        const items = Array.isArray(data) ? data : data.items || [];
        setEvents(items);
        setTotal(Number.isFinite(data.total) ? data.total : items.length);
      } catch (err) {
        if (!mounted) return;
        setEvents([]);
        setTotal(0);
        setError(err.message || "Unable to load security events");
      } finally {
        if (mounted) setLoading(false);
      }
    }
    loadEvents();
    return () => {
      mounted = false;
    };
  }, [debouncedFilters, timeWindow]);

  return (
    <div className="stack">
      <section className="card events-header">
        <div>
          <h2 className="section-title">Security Events</h2>
          <p className="subtle">Review logins, threats, integrity, and bot activity.</p>
        </div>
        <div className="events-tenant">
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
        <div className="events-tabs">
          {CATEGORY_TABS.map((tab) => (
            <button
              key={tab.value}
              className={`btn secondary ${category === tab.value ? "active" : ""}`}
              onClick={() => setCategory(tab.value)}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <div className="controls-grid events-filters">
          <div className="field">
            <label className="label">
              Time range{" "}
              {hasHistoryLimit && (
                <span className="badge pro" title="Upgrade to unlock longer history.">
                  Pro
                </span>
              )}
            </label>
            <select className="select" value={rangeValue} onChange={handleRangeChange}>
              {rangeOptions.map((option) => (
                <option key={option.value} value={option.value} disabled={option.disabled}>
                  {option.label}
                </option>
              ))}
            </select>
            {timeClampNotice && <div className="help">{timeClampNotice}</div>}
            {!timeClampNotice && hasHistoryLimit && (
              <div className="help">Upgrade to unlock longer history windows.</div>
            )}
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
            <label className="label">Environment</label>
            <select
              className="select"
              value={envId}
              onChange={(e) => setEnvId(e.target.value)}
              disabled={!environments.length}
            >
              <option value="">All environments</option>
              {environments.map((env) => (
                <option key={env.id} value={env.id}>
                  {env.name}
                </option>
              ))}
            </select>
            {!environments.length && (
              <div className="help">Select a website to load environments.</div>
            )}
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
        {(ipHash || countryCode) && (
          <div className="events-pills">
            {ipHash && (
              <span className="events-pill">
                IP hash: {maskHash(ipHash)}
                <button className="btn secondary small" onClick={() => setIpHash("")}>
                  Clear
                </button>
              </span>
            )}
            {countryCode && (
              <span className="events-pill">
                Country: {countryCode}
                <button className="btn secondary small" onClick={() => setCountryCode("")}>
                  Clear
                </button>
              </span>
            )}
          </div>
        )}
      </section>

      <section className="card">
        <div className="events-table-header">
          <div>
            <h3 className="section-title">Events</h3>
            <div className="subtle">
              {total ? `Showing ${events.length} of ${total}` : "No events yet."}
            </div>
          </div>
        </div>
        {loading && <p className="subtle">Loading events...</p>}
        {error && <p className="error-text">{error}</p>}
        {!loading && !error && !events.length && (
          <p className="subtle">No matching security events for this window.</p>
        )}
        {!loading && !error && events.length > 0 && (
          <table className="table events-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Category</th>
                <th>Event</th>
                <th>Severity</th>
                <th>Path</th>
                <th>Status</th>
                <th>IP hash</th>
                <th>Location</th>
                {hasAsnGranularity && <th>ASN</th>}
                <th>Map</th>
              </tr>
            </thead>
            <tbody>
              {events.map((item) => (
                <tr key={item.id}>
                  <td>{formatDateTime(item.event_ts || item.created_at)}</td>
                  <td>{formatCategoryLabel(item.category)}</td>
                  <td className="event-type">{formatEventType(item.event_type)}</td>
                  <td>{item.severity || "--"}</td>
                  <td>{item.request_path || "--"}</td>
                  <td>{item.status_code || "--"}</td>
                  <td>{item.ip_hash || "--"}</td>
                  <td>{formatLocation(item) || "--"}</td>
                  {hasAsnGranularity && (
                    <td>{item.asn_number ? `AS${item.asn_number}` : "--"}</td>
                  )}
                  <td>
                    <button
                      className="btn secondary small"
                      onClick={() => navigateTo(buildMapLink(item))}
                    >
                      View on map
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
