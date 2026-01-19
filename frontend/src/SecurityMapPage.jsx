import { useEffect, useMemo, useState } from "react";
import { apiFetch, ACTIVE_TENANT_KEY } from "./api";
import GeoMapView from "./GeoMapView";

const TIME_RANGES = [
  { value: "24h", label: "Last 24 hours", days: 1 },
  { value: "7d", label: "Last 7 days", days: 7 },
  { value: "30d", label: "Last 30 days", days: 30 },
];

const CATEGORY_OPTIONS = [
  { value: "behaviour", label: "Behaviour" },
  { value: "login", label: "Logins" },
  { value: "threat", label: "Threats" },
  { value: "error", label: "Errors" },
  { value: "audit", label: "Audit" },
];

const CATEGORY_LABELS = CATEGORY_OPTIONS.reduce((acc, item) => {
  acc[item.value] = item.label;
  return acc;
}, {});

const SEVERITY_OPTIONS = [
  { value: "", label: "Any severity" },
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
];

const formatCategoryLabel = (value) =>
  CATEGORY_LABELS[value] || value || "All activity";

const estimateRadiusKm = (count) => {
  if (!count || Number.isNaN(count)) return 80;
  const scaled = Math.sqrt(count) * 12;
  return Math.min(300, Math.max(60, scaled));
};

const formatCount = (value) =>
  typeof value === "number" ? value.toLocaleString() : "0";

const formatDateTime = (value) => {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString();
};

const truncateHash = (value) => {
  if (!value) return "";
  if (value.length <= 12) return value;
  return `${value.slice(0, 6)}...${value.slice(-4)}`;
};

const formatLatLon = (lat, lon) => {
  if (lat == null || lon == null) return "Country-level";
  return `${lat.toFixed(2)}, ${lon.toFixed(2)}`;
};

export default function SecurityMapPage() {
  const [tenants, setTenants] = useState([]);
  const [activeTenant, setActiveTenant] = useState(
    localStorage.getItem(ACTIVE_TENANT_KEY) || ""
  );
  const [websites, setWebsites] = useState([]);
  const [environments, setEnvironments] = useState([]);
  const [websiteId, setWebsiteId] = useState("");
  const [envId, setEnvId] = useState("");
  const [range, setRange] = useState("24h");
  const [category, setCategory] = useState("behaviour");
  const [severity, setSeverity] = useState("");
  const [summary, setSummary] = useState([]);
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [error, setError] = useState("");
  const [planLimited, setPlanLimited] = useState(false);
  const [viewMode, setViewMode] = useState("map");
  const [debouncedFilters, setDebouncedFilters] = useState({
    activeTenant,
    websiteId,
    envId,
    range,
    category,
    severity,
  });
  const [drilldownOpen, setDrilldownOpen] = useState(false);
  const [drilldownSelection, setDrilldownSelection] = useState(null);
  const [drilldownLoading, setDrilldownLoading] = useState(false);
  const [drilldownError, setDrilldownError] = useState("");
  const [drilldownData, setDrilldownData] = useState(null);

  const activeTenantLabel = useMemo(() => {
    const found = tenants.find((tenant) => String(tenant.slug) === activeTenant);
    return found ? found.name : "";
  }, [tenants, activeTenant]);

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
    const handle = setTimeout(() => {
      setDebouncedFilters({
        activeTenant,
        websiteId,
        envId,
        range,
        category,
        severity,
      });
    }, 300);
    return () => clearTimeout(handle);
  }, [activeTenant, websiteId, envId, range, category, severity]);

  const timeWindow = useMemo(() => {
    const entry =
      TIME_RANGES.find((item) => item.value === debouncedFilters.range) ||
      TIME_RANGES[0];
    const to = new Date();
    const from = new Date(Date.now() - entry.days * 24 * 60 * 60 * 1000);
    return { from, to };
  }, [debouncedFilters.range]);

  useEffect(() => {
    if (!debouncedFilters.activeTenant) return;
    let mounted = true;
    async function loadSummary() {
      setLoadingSummary(true);
      setError("");
      try {
        const params = new URLSearchParams();
        params.set("from", timeWindow.from.toISOString());
        params.set("to", timeWindow.to.toISOString());
        if (debouncedFilters.websiteId) {
          params.set("website_id", debouncedFilters.websiteId);
        }
        if (debouncedFilters.envId) params.set("env_id", debouncedFilters.envId);
        if (debouncedFilters.category) {
          params.set("category", debouncedFilters.category);
        }
        if (debouncedFilters.severity) {
          params.set("severity", debouncedFilters.severity);
        }
        const resp = await apiFetch(`/api/v1/map/summary?${params.toString()}`);
        if (!resp.ok) {
          throw new Error("Unable to load map summary");
        }
        const data = await resp.json();
        if (!mounted) return;
        const items = data.items || [];
        setSummary(items);
        setPlanLimited(
          items.length > 0 &&
            items.every((point) => point.latitude == null && point.longitude == null)
        );
      } catch (err) {
        if (!mounted) return;
        setSummary([]);
        setPlanLimited(false);
        setError(err.message || "Unable to load map summary");
      } finally {
        if (mounted) setLoadingSummary(false);
      }
    }
    loadSummary();
    return () => {
      mounted = false;
    };
  }, [debouncedFilters, timeWindow]);

  useEffect(() => {
    setDrilldownOpen(false);
    setDrilldownSelection(null);
    setDrilldownData(null);
    setDrilldownError("");
  }, [activeTenant]);

  useEffect(() => {
    if (!drilldownOpen || !drilldownSelection || !debouncedFilters.activeTenant) {
      setDrilldownData(null);
      return;
    }
    let mounted = true;
    async function loadDrilldown() {
      setDrilldownLoading(true);
      setDrilldownError("");
      setDrilldownData(null);
      try {
        const params = new URLSearchParams();
        params.set("from", timeWindow.from.toISOString());
        params.set("to", timeWindow.to.toISOString());
        if (debouncedFilters.websiteId) {
          params.set("website_id", debouncedFilters.websiteId);
        }
        if (debouncedFilters.envId) params.set("env_id", debouncedFilters.envId);
        if (debouncedFilters.category) {
          params.set("category", debouncedFilters.category);
        }
        if (debouncedFilters.severity) {
          params.set("severity", debouncedFilters.severity);
        }
        if (
          drilldownSelection.type === "country" &&
          drilldownSelection.countryCode
        ) {
          params.set("country_code", drilldownSelection.countryCode);
        }
        if (drilldownSelection.type === "radius") {
          const lat = drilldownSelection.lat;
          const lon = drilldownSelection.lon;
          if (lat != null && lon != null) {
            params.set("lat", String(lat));
            params.set("lon", String(lon));
            params.set(
              "radius_km",
              String(Math.round(drilldownSelection.radiusKm || 80))
            );
          }
        }
        const resp = await apiFetch(`/api/v1/map/drilldown?${params.toString()}`);
        if (!resp.ok) {
          throw new Error("Unable to load drilldown");
        }
        const data = await resp.json();
        if (!mounted) return;
        setDrilldownData(data);
      } catch (err) {
        if (!mounted) return;
        setDrilldownError(err.message || "Unable to load drilldown");
      } finally {
        if (mounted) setDrilldownLoading(false);
      }
    }
    loadDrilldown();
    return () => {
      mounted = false;
    };
  }, [drilldownOpen, drilldownSelection, debouncedFilters, timeWindow]);

  const handleDrilldownSelect = (selection) => {
    if (!selection) return;
    setDrilldownSelection(selection);
    setDrilldownOpen(true);
  };

  const handleListSelect = (point) => {
    if (point.latitude != null && point.longitude != null) {
      handleDrilldownSelect({
        type: "radius",
        lat: point.latitude,
        lon: point.longitude,
        radiusKm: estimateRadiusKm(point.count),
        label: point.city || point.country_code || "Unknown",
        count: point.count,
      });
      return;
    }
    if (point.country_code) {
      handleDrilldownSelect({
        type: "country",
        countryCode: point.country_code,
        label: point.country_code,
        count: point.count,
      });
    }
  };

  const totalCount = useMemo(() => {
    if (!drilldownData) return 0;
    if (typeof drilldownData.total_count === "number") {
      return drilldownData.total_count;
    }
    const source = (drilldownData.countries || []).length
      ? drilldownData.countries
      : drilldownData.cities || [];
    return source.reduce((sum, item) => sum + (item.count || 0), 0);
  }, [drilldownData]);

  const lastSeenLabel = useMemo(() => {
    if (!drilldownData) return "";
    if (drilldownData.last_seen) {
      return formatDateTime(drilldownData.last_seen);
    }
    return "";
  }, [drilldownData]);

  const categoryBreakdown = useMemo(() => {
    if (!drilldownData) return [];
    if (Array.isArray(drilldownData.category_breakdown)) {
      if (drilldownData.category_breakdown.length) {
        return drilldownData.category_breakdown;
      }
    }
    if (debouncedFilters.category) {
      return [{ category: debouncedFilters.category, count: totalCount }];
    }
    return [];
  }, [drilldownData, debouncedFilters.category, totalCount]);

  const selectionTitle = useMemo(() => {
    if (!drilldownSelection) return "No selection";
    return (
      drilldownSelection.label ||
      drilldownSelection.countryCode ||
      "Selected area"
    );
  }, [drilldownSelection]);

  const selectionDetail = useMemo(() => {
    if (!drilldownSelection) return "Select a cluster to drill down.";
    if (drilldownSelection.type === "country") {
      return `Country code: ${drilldownSelection.countryCode || "Unknown"}`;
    }
    const lat = drilldownSelection.lat?.toFixed(2);
    const lon = drilldownSelection.lon?.toFixed(2);
    const radius = Math.round(drilldownSelection.radiusKm || 80);
    return `Lat ${lat}, Lon ${lon} - ${radius} km radius`;
  }, [drilldownSelection]);

  const drilldownHasContent = useMemo(() => {
    if (!drilldownData) return false;
    return [
      drilldownData.countries,
      drilldownData.cities,
      drilldownData.asns,
      drilldownData.ip_hashes,
      drilldownData.paths,
    ].some((list) => Array.isArray(list) && list.length > 0);
  }, [drilldownData]);

  return (
    <div className="stack">
      <section className="card map-header">
        <div className="map-header-content">
          <div>
            <h2 className="section-title">Geo Activity Map</h2>
            <p className="subtle">
              Estimated locations of logins, threats, and anomalies.
            </p>
          </div>
          <div className="map-tenant">
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
            {activeTenantLabel && (
              <div className="help">Viewing {activeTenantLabel}</div>
            )}
          </div>
        </div>
      </section>

      <section className="card">
        <div className="controls-grid">
          <div className="field">
            <label className="label">Time range</label>
            <select
              className="select"
              value={range}
              onChange={(e) => setRange(e.target.value)}
            >
              {TIME_RANGES.map((option) => (
                <option key={option.value} value={option.value}>
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
        </div>
      </section>

      {planLimited && (
        <section className="card map-upgrade">
          <strong>Upgrade to unlock full geo precision.</strong>
          <p className="subtle">
            Your plan currently limits geo results to country-level summaries.
          </p>
        </section>
      )}

      <section className="map-grid">
        <div className="card map-panel">
          <div className="map-panel-header">
            <div>
              <h3 className="section-title">Map canvas</h3>
              <p className="subtle">Clustered activity view based on geo aggregates.</p>
            </div>
            <div className="map-view-toggle">
              <button
                className={`btn secondary ${viewMode === "map" ? "active" : ""}`}
                onClick={() => setViewMode("map")}
              >
                Map
              </button>
              <button
                className={`btn secondary ${viewMode === "list" ? "active" : ""}`}
                onClick={() => setViewMode("list")}
              >
                List
              </button>
            </div>
          </div>

          {viewMode === "map" ? (
            <GeoMapView
              points={summary}
              category={category}
              loading={loadingSummary}
              error={error}
              planLimited={planLimited}
              onSelect={handleDrilldownSelect}
            />
          ) : (
            <div className="map-summary-list">
              {loadingSummary && <p className="subtle">Loading map summary...</p>}
              {error && <p className="error-text">{error}</p>}
              {!loadingSummary && !error && summary.length === 0 && (
                <p className="subtle">No activity found for this time window.</p>
              )}
              {!loadingSummary &&
                !error &&
                summary.map((point, idx) => {
                  const canDrill =
                    point.latitude != null || point.longitude != null || point.country_code;
                  return (
                    <div
                      key={`${point.country_code}-${idx}`}
                      className="map-summary-item"
                    >
                      <div>
                        <strong>{formatCount(point.count)}</strong>{" "}
                        <span className="subtle">
                          {point.city || point.country_code || "Unknown"}
                        </span>
                        <div className="subtle">
                          {formatLatLon(point.latitude, point.longitude)}
                        </div>
                      </div>
                      <button
                        className="btn secondary small"
                        onClick={() => handleListSelect(point)}
                        disabled={!canDrill}
                      >
                        Drilldown
                      </button>
                    </div>
                  );
                })}
            </div>
          )}
        </div>

        <aside className="card map-panel map-drilldown">
          <div className="map-panel-header">
            <div>
              <h3 className="section-title">Drilldown</h3>
              <p className="subtle">
                Click a cluster or list row to inspect countries, ASN, and IP hashes.
              </p>
            </div>
            {drilldownOpen && (
              <button
                className="btn secondary small"
                onClick={() => setDrilldownOpen(false)}
              >
                Close
              </button>
            )}
          </div>

          {!drilldownOpen && (
            <div className="map-drilldown-placeholder">
              <div className="muted">No drilldown selected yet.</div>
            </div>
          )}

          {drilldownOpen && (
            <div className="map-drilldown-body">
              <div className="map-drilldown-meta">
                <div className="map-drilldown-kicker">Selection</div>
                <div className="map-drilldown-title">{selectionTitle}</div>
                <div className="subtle">{selectionDetail}</div>
              </div>

              {planLimited && (
                <div className="map-drilldown-upgrade">
                  Upgrade to see city-level, ASN, and IP hash detail.
                </div>
              )}

              {drilldownLoading && (
                <div className="map-drilldown-loading">Loading drilldown...</div>
              )}
              {drilldownError && !drilldownLoading && (
                <p className="error-text">{drilldownError}</p>
              )}

              {!drilldownLoading && !drilldownError && drilldownData && (
                <>
                  <div className="map-drilldown-section">
                    <div className="map-drilldown-section-title">Overview</div>
                    <div className="map-drilldown-row">
                      <span>Total activity</span>
                      <strong>{formatCount(totalCount)}</strong>
                    </div>
                    <div className="map-drilldown-row">
                      <span>Range</span>
                      <span>
                        {timeWindow.from.toLocaleDateString()} -{" "}
                        {timeWindow.to.toLocaleDateString()}
                      </span>
                    </div>
                    {lastSeenLabel && (
                      <div className="map-drilldown-row">
                        <span>Latest bucket</span>
                        <span>{lastSeenLabel}</span>
                      </div>
                    )}
                  </div>

                  <div className="map-drilldown-section">
                    <div className="map-drilldown-section-title">Category breakdown</div>
                    {categoryBreakdown.length ? (
                      <div className="map-drilldown-list">
                        {categoryBreakdown.map((entry) => (
                          <div
                            key={entry.category}
                            className="map-drilldown-row"
                          >
                            <span>{formatCategoryLabel(entry.category)}</span>
                            <span>{formatCount(entry.count)}</span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="map-drilldown-empty">
                        No category breakdown available yet.
                      </div>
                    )}
                  </div>

                  <div className="map-drilldown-section">
                    <div className="map-drilldown-section-title">Top countries</div>
                    {drilldownData.countries?.length ? (
                      <div className="map-drilldown-list">
                        {drilldownData.countries.map((item) => (
                          <div
                            key={item.country_code || "unknown"}
                            className="map-drilldown-row"
                          >
                            <span>{item.country_code || "Unknown"}</span>
                            <span>{formatCount(item.count)}</span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="map-drilldown-empty">No country data.</div>
                    )}
                  </div>

                  <div className="map-drilldown-section">
                    <div className="map-drilldown-section-title">Top cities</div>
                    {planLimited ? (
                      <div className="map-drilldown-empty">
                        City-level detail requires a geo-enabled plan.
                      </div>
                    ) : drilldownData.cities?.length ? (
                      <div className="map-drilldown-list">
                        {drilldownData.cities.slice(0, 10).map((item, idx) => (
                          <div key={`${item.city}-${idx}`} className="map-drilldown-row">
                            <span>
                              {item.city || "Unknown"}
                              {item.region ? `, ${item.region}` : ""}
                            </span>
                            <span>{formatCount(item.count)}</span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="map-drilldown-empty">No city data.</div>
                    )}
                  </div>

                  <div className="map-drilldown-section">
                    <div className="map-drilldown-section-title">Top ASNs</div>
                    {planLimited ? (
                      <div className="map-drilldown-empty">
                        ASN detail requires a geo-enabled plan.
                      </div>
                    ) : drilldownData.asns?.length ? (
                      <div className="map-drilldown-list">
                        {drilldownData.asns.slice(0, 10).map((item, idx) => (
                          <div key={`${item.asn_number}-${idx}`} className="map-drilldown-row">
                            <span>
                              {item.asn_number ? `AS${item.asn_number}` : "ASN"}
                              {item.asn_org ? ` · ${item.asn_org}` : ""}
                            </span>
                            <span>{formatCount(item.count)}</span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="map-drilldown-empty">No ASN data.</div>
                    )}
                  </div>

                  <div className="map-drilldown-section">
                    <div className="map-drilldown-section-title">Top IP hashes</div>
                    {planLimited ? (
                      <div className="map-drilldown-empty">
                        IP hash detail requires a geo-enabled plan.
                      </div>
                    ) : drilldownData.ip_hashes?.length ? (
                      <div className="map-drilldown-list">
                        {drilldownData.ip_hashes.slice(0, 10).map((item) => (
                          <div key={item.ip_hash} className="map-drilldown-row">
                            <span title={item.ip_hash}>{truncateHash(item.ip_hash)}</span>
                            <span>{formatCount(item.count)}</span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="map-drilldown-empty">No IP hash data.</div>
                    )}
                  </div>

                  <div className="map-drilldown-section">
                    <div className="map-drilldown-section-title">Top paths</div>
                    {planLimited ? (
                      <div className="map-drilldown-empty">
                        Path breakdown requires a geo-enabled plan.
                      </div>
                    ) : drilldownData.paths?.length ? (
                      <div className="map-drilldown-list">
                        {drilldownData.paths.slice(0, 8).map((item) => (
                          <div key={item.path} className="map-drilldown-row">
                            <span>{item.path}</span>
                            <span>{formatCount(item.count)}</span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="map-drilldown-empty">No path data.</div>
                    )}
                  </div>

                  <div className="map-drilldown-actions">
                    <button className="btn secondary small" disabled>
                      View related events (coming soon)
                    </button>
                  </div>
                </>
              )}

              {!drilldownLoading &&
                !drilldownError &&
                drilldownOpen &&
                !drilldownData &&
                !drilldownHasContent && (
                  <div className="map-drilldown-empty">
                    No drilldown data available yet.
                  </div>
                )}
            </div>
          )}
        </aside>
      </section>
    </div>
  );
}
