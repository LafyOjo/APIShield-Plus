import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch, ACTIVE_TENANT_KEY } from "./api";
import TourOverlay from "./TourOverlay";
import { useTour } from "./useTour";
import DemoDataToggle from "./DemoDataToggle";
import { useDemoData } from "./useDemoData";
import PaywallCard from "./components/PaywallCard";

const TIME_RANGES = [
  { value: "24h", label: "Last 24 hours", days: 1 },
  { value: "7d", label: "Last 7 days", days: 7 },
  { value: "30d", label: "Last 30 days", days: 30 },
];

const DAY_MS = 24 * 60 * 60 * 1000;
const CUSTOM_RANGE_VALUE = "custom";
const TIME_RANGE_TOLERANCE_MS = 15 * 60 * 1000;
const SITE_PATH_SENTINEL = "__site__";

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

const parsePathParam = (value) => {
  if (!value) return "";
  return value === SITE_PATH_SENTINEL ? SITE_PATH_SENTINEL : value;
};

const getPathKey = (path) => (path == null ? SITE_PATH_SENTINEL : path);

const formatPathLabel = (path) => (path == null ? "Site-wide" : path);

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

const formatPercent = (value) => {
  if (value == null || Number.isNaN(value)) return "--";
  return `${(value * 100).toFixed(1)}%`;
};

const formatFactorLabel = (value) => {
  if (!value) return "--";
  return String(value).replace(/_/g, " ");
};

const trustScoreClass = (value) => {
  if (value == null) return "neutral";
  if (value >= 80) return "good";
  if (value >= 60) return "warn";
  return "risk";
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
    pathKey: parsePathParam(params.get("path")),
  };
};

export default function RevenueLeakHeatmapPage() {
  const initialFilters = useMemo(() => getInitialFilters(), []);
  const [tenants, setTenants] = useState([]);
  const [activeTenant, setActiveTenant] = useState(
    localStorage.getItem(ACTIVE_TENANT_KEY) || ""
  );
  const [websites, setWebsites] = useState([]);
  const [websiteId, setWebsiteId] = useState(initialFilters.websiteId);
  const [fromTs, setFromTs] = useState(initialFilters.from);
  const [toTs, setToTs] = useState(initialFilters.to);
  const [selectedPathKey, setSelectedPathKey] = useState(initialFilters.pathKey);
  const [leaks, setLeaks] = useState([]);
  const [series, setSeries] = useState([]);
  const [seriesSummary, setSeriesSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [seriesLoading, setSeriesLoading] = useState(false);
  const [error, setError] = useState("");
  const [shareStatus, setShareStatus] = useState("");
  const [leakEnabled, setLeakEnabled] = useState(true);
  const [leakUpgradeNote, setLeakUpgradeNote] = useState("");
  const { enabled: includeDemo, setEnabled: setIncludeDemo } = useDemoData();
  const [debouncedFilters, setDebouncedFilters] = useState({
    activeTenant,
    websiteId,
    from: fromTs,
    to: toTs,
    includeDemo,
  });
  const leaksTour = useTour("leaks", activeTenant);

  const leaksTourSteps = useMemo(
    () => [
      {
        selector: '[data-tour="leaks-table"]',
        title: "Top leaking pages",
        body: "Focus on the pages losing the most revenue first.",
      },
      {
        selector: '[data-tour="leaks-factors"]',
        title: "Trust factors explain why",
        body: "Trust signals highlight what caused the conversion drop.",
      },
      {
        selector: '[data-tour="leaks-investigate"]',
        title: "Investigate in context",
        body: "Jump into incidents or the map with filters pre-applied.",
      },
    ],
    []
  );

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

  const handleShare = async () => {
    const shareUrl = window.location.href;
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(shareUrl);
        setShareStatus("Link copied.");
      } else {
        window.prompt("Copy this link:", shareUrl);
        setShareStatus("Link ready to copy.");
      }
    } catch (err) {
      setShareStatus("Unable to copy link.");
    }
  };

  const buildIncidentListLink = useCallback(() => {
    if (!isValidDate(fromTs) || !isValidDate(toTs)) {
      return "/dashboard/revenue-integrity/incidents";
    }
    const params = new URLSearchParams();
    params.set("from", fromTs.toISOString());
    params.set("to", toTs.toISOString());
    if (websiteId) params.set("website_id", websiteId);
    if (includeDemo) params.set("demo", "1");
    return `/dashboard/revenue-integrity/incidents?${params.toString()}`;
  }, [fromTs, toTs, websiteId, includeDemo]);

  const buildMapLink = useCallback(() => {
    if (!isValidDate(fromTs) || !isValidDate(toTs)) {
      return "/dashboard/security/map";
    }
    const params = new URLSearchParams();
    params.set("from", fromTs.toISOString());
    params.set("to", toTs.toISOString());
    if (websiteId) params.set("website_id", websiteId);
    if (includeDemo) params.set("demo", "1");
    return `/dashboard/security/map?${params.toString()}`;
  }, [fromTs, toTs, websiteId, includeDemo]);

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
        const resp = await apiFetch("/api/v1/entitlements");
        if (!resp.ok) {
          throw new Error("Unable to load entitlements");
        }
        const data = await resp.json();
        if (!mounted) return;
        const entitlements = data?.entitlements || {};
        const features = entitlements.features || {};
        const enabled = typeof features.revenue_leaks === "boolean" ? features.revenue_leaks : true;
        setLeakEnabled(enabled);
        setLeakUpgradeNote(
          enabled ? "" : "Revenue Leak Heatmap is a Pro feature. Upgrade to unlock it."
        );
      } catch (err) {
        if (!mounted) return;
        setLeakEnabled(true);
        setLeakUpgradeNote("");
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
        from: fromTs,
        to: toTs,
        includeDemo,
      });
    }, 250);
    return () => clearTimeout(handle);
  }, [activeTenant, websiteId, fromTs, toTs, includeDemo]);

  useEffect(() => {
    if (!isValidDate(fromTs) || !isValidDate(toTs)) return;
    const params = new URLSearchParams();
    params.set("from", fromTs.toISOString());
    params.set("to", toTs.toISOString());
    if (websiteId) params.set("website_id", websiteId);
    if (selectedPathKey) params.set("path", selectedPathKey);
    if (includeDemo) params.set("demo", "1");
    const nextUrl = `${window.location.pathname}?${params.toString()}${window.location.hash || ""}`;
    window.history.replaceState({}, "", nextUrl);
  }, [fromTs, toTs, websiteId, selectedPathKey, includeDemo]);

  useEffect(() => {
    if (!debouncedFilters.activeTenant) return;
    if (!leakEnabled) {
      setLeaks([]);
      setSeries([]);
      setSeriesSummary(null);
      return;
    }
    let mounted = true;
    async function loadLeaks() {
      setLoading(true);
      setError("");
      try {
        const params = new URLSearchParams();
        params.set("from", debouncedFilters.from.toISOString());
        params.set("to", debouncedFilters.to.toISOString());
        if (debouncedFilters.websiteId) {
          params.set("website_id", debouncedFilters.websiteId);
        }
        params.set("limit", "15");
        if (debouncedFilters.includeDemo) {
          params.set("include_demo", "true");
        }
        const resp = await apiFetch(`/api/v1/revenue/leaks?${params.toString()}`);
        if (resp.status === 403) {
          throw new Error("Revenue Leak Heatmap is a Pro feature.");
        }
        if (!resp.ok) {
          throw new Error("Unable to load revenue leaks");
        }
        const data = await resp.json();
        if (!mounted) return;
        const items = Array.isArray(data?.items) ? data.items : [];
        setLeaks(items);
        if (!selectedPathKey && items.length) {
          setSelectedPathKey(getPathKey(items[0].path));
        }
      } catch (err) {
        if (!mounted) return;
        setLeaks([]);
        setError(err.message || "Unable to load revenue leaks");
      } finally {
        if (mounted) setLoading(false);
      }
    }
    loadLeaks();
    return () => {
      mounted = false;
    };
  }, [debouncedFilters, leakEnabled]);

  useEffect(() => {
    if (!leaks.length) {
      setSelectedPathKey("");
      return;
    }
    const exists = leaks.some((item) => getPathKey(item.path) === selectedPathKey);
    if (!exists) {
      setSelectedPathKey(getPathKey(leaks[0].path));
    }
  }, [leaks, selectedPathKey]);

  useEffect(() => {
    if (!debouncedFilters.activeTenant || !selectedPathKey) {
      setSeries([]);
      setSeriesSummary(null);
      return;
    }
    if (!leakEnabled) {
      setSeries([]);
      setSeriesSummary(null);
      return;
    }
    let mounted = true;
    async function loadSeries() {
      setSeriesLoading(true);
      try {
        const params = new URLSearchParams();
        params.set("from", debouncedFilters.from.toISOString());
        params.set("to", debouncedFilters.to.toISOString());
        if (debouncedFilters.websiteId) {
          params.set("website_id", debouncedFilters.websiteId);
        }
        params.set("path", selectedPathKey);
        if (debouncedFilters.includeDemo) {
          params.set("include_demo", "true");
        }
        const resp = await apiFetch(`/api/v1/revenue/leaks?${params.toString()}`);
        if (resp.status === 403) {
          throw new Error("Revenue Leak Heatmap is a Pro feature.");
        }
        if (!resp.ok) {
          throw new Error("Unable to load revenue timeline");
        }
        const data = await resp.json();
        if (!mounted) return;
        setSeries(Array.isArray(data?.series) ? data.series : []);
        const items = Array.isArray(data?.items) ? data.items : [];
        setSeriesSummary(items.length ? items[0] : null);
      } catch (err) {
        if (!mounted) return;
        setSeries([]);
        setSeriesSummary(null);
      } finally {
        if (mounted) setSeriesLoading(false);
      }
    }
    loadSeries();
    return () => {
      mounted = false;
    };
  }, [debouncedFilters, selectedPathKey, leakEnabled]);

  const selectedLeak = useMemo(() => {
    if (!selectedPathKey) return null;
    const fromList = leaks.find(
      (item) => getPathKey(item.path) === selectedPathKey
    );
    return fromList || seriesSummary || null;
  }, [leaks, seriesSummary, selectedPathKey]);

  const timelineMax = useMemo(() => {
    if (!series.length) return 0;
    return series.reduce((max, point) => {
      const value = point.estimated_lost_revenue || 0;
      return value > max ? value : max;
    }, 0);
  }, [series]);

  return (
    <div className="stack">
      <section className="card leaks-header">
        <div>
          <h2 className="section-title">Revenue Leak Heatmap</h2>
          <p className="subtle">
            Rank pages by estimated lost revenue and connect trust signals to drop-offs.
          </p>
          <div className="row revenue-nav">
            <button className="btn secondary nav-tab active">Leak Heatmap</button>
            <button
              className="btn secondary nav-tab"
              onClick={() => navigateTo("/dashboard/revenue-integrity/incidents")}
            >
              Incidents
            </button>
            <button className="btn secondary" onClick={leaksTour.restart}>
              Start tour
            </button>
          </div>
        </div>
        <div className="leaks-tenant">
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

      {!leakEnabled && (
        <PaywallCard
          title="Revenue Leak Heatmap is Pro"
          subtitle={leakUpgradeNote}
          bullets={[
            "Rank leaking pages by lost revenue.",
            "Connect trust signals to conversion drop-offs.",
            "Investigate incidents with pre-filtered context.",
          ]}
          previewTitle="Preview"
          preview={
            <div className="paywall-preview-list">
              <div className="paywall-preview-row">
                <span>/checkout</span>
                <span>$2,400</span>
              </div>
              <div className="paywall-preview-row">
                <span>/pricing</span>
                <span>$1,120</span>
              </div>
              <div className="paywall-preview-row">
                <span>/login</span>
                <span>$680</span>
              </div>
            </div>
          }
          featureKey="revenue_leaks"
          source="revenue_leak_heatmap"
          planKey="pro"
          showDismiss={false}
          className="card"
        />
      )}

      <section className="card">
        <div className="controls-grid leaks-filters">
          <div className="field">
            <label className="label">Time range</label>
            <select
              className="select"
              value={rangeValue}
              onChange={(e) => {
                const selected = TIME_RANGES.find(
                  (option) => option.value === e.target.value
                );
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
            <label className="label">Share</label>
            <button className="btn secondary" onClick={handleShare}>
              Copy link
            </button>
            {shareStatus && <div className="help">{shareStatus}</div>}
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

      <section className="card" data-tour="leaks-table">
        <div className="leaks-table-header">
          <div>
            <h3 className="section-title">Top leaking pages</h3>
            <div className="subtle">
              {leaks.length ? `${leaks.length} paths` : "No leaks yet."}
            </div>
          </div>
        </div>
        {loading && <p className="subtle">Loading leak summary...</p>}
        {error && <p className="error-text">{error}</p>}
        {!loading && !error && leaks.length === 0 && (
          <p className="subtle">No leak estimates found in this window.</p>
        )}
        {!loading && !error && leaks.length > 0 && (
          <table className="table leaks-table">
            <thead>
              <tr>
                <th>Path</th>
                <th>Est. lost revenue</th>
                <th>Trust score</th>
                <th>Conversion rate</th>
                <th>Top factors</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {leaks.map((item) => {
                const key = getPathKey(item.path);
                const isActive = key === selectedPathKey;
                const trustDelta =
                  item.trust_score_delta != null
                    ? `${item.trust_score_delta > 0 ? "+" : ""}${item.trust_score_delta}`
                    : "--";
                return (
                  <tr key={`${key}-${item.website_id}-${item.environment_id}`}>
                    <td>
                      <div className="leak-path">{formatPathLabel(item.path)}</div>
                      <div className="subtle">Site #{item.website_id}</div>
                    </td>
                    <td>{formatCurrency(item.total_lost_revenue)}</td>
                    <td>
                      <span className={`trust-chip ${trustScoreClass(item.trust_score_latest)}`}>
                        {item.trust_score_latest ?? "--"}
                      </span>
                      <div className="subtle">Delta {trustDelta}</div>
                    </td>
                    <td>
                      <div>{formatPercent(item.observed_conversion_rate)}</div>
                      <div className="subtle">
                        Baseline {formatPercent(item.baseline_conversion_rate)}
                      </div>
                    </td>
                    <td>
                      <div className="leak-factor-badges">
                        {(item.top_factors || []).slice(0, 3).map((factor) => (
                          <span
                            key={`${factor.factor_type}-${factor.severity}`}
                            className={`factor-badge ${factor.severity || "medium"}`}
                            title={formatFactorLabel(factor.factor_type)}
                          >
                            {formatFactorLabel(factor.factor_type)}
                          </span>
                        ))}
                        {!item.top_factors?.length && (
                          <span className="subtle">No factors</span>
                        )}
                      </div>
                    </td>
                    <td>
                      <button
                        className={`btn secondary small ${isActive ? "active" : ""}`}
                        onClick={() => setSelectedPathKey(key)}
                      >
                        Inspect
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>

      <section className="leaks-grid">
        <div className="card leak-panel">
          <div className="leak-panel-header">
            <div>
              <h3 className="section-title">Timeline</h3>
              <p className="subtle">
                Lost revenue vs trust score for {selectedLeak ? formatPathLabel(selectedLeak.path) : "selected path"}.
              </p>
            </div>
            <div className="row">
              <button className="btn secondary small" onClick={() => navigateTo(buildIncidentListLink())}>
                View incidents
              </button>
              <button
                className="btn secondary small"
                data-tour="leaks-investigate"
                onClick={() => navigateTo(buildMapLink())}
              >
                View on map
              </button>
            </div>
          </div>
          {seriesLoading && <p className="subtle">Loading timeline...</p>}
          {!seriesLoading && !series.length && (
            <p className="subtle">Select a path to see the timeline.</p>
          )}
          {!seriesLoading && series.length > 0 && (
            <div className="leak-timeline">
              {series.map((point) => {
                const lostValue = point.estimated_lost_revenue || 0;
                const widthPct = timelineMax ? Math.max(4, (lostValue / timelineMax) * 100) : 4;
                return (
                  <div key={point.bucket_start} className="leak-timeline-row">
                    <div className="leak-timeline-time">{formatDateTime(point.bucket_start)}</div>
                    <div className="leak-timeline-bar-wrap">
                      <div className="leak-timeline-bar" style={{ width: `${widthPct}%` }} />
                    </div>
                    <div className="leak-timeline-metrics">
                      <span className="leak-timeline-revenue">{formatCurrency(lostValue)}</span>
                      <span className={`trust-chip ${trustScoreClass(point.trust_score)}`}>
                        {point.trust_score ?? "--"}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <aside className="card leak-panel" data-tour="leaks-factors">
          <div className="leak-panel-header">
            <div>
              <h3 className="section-title">Why this leaks</h3>
              <p className="subtle">Signals and evidence tied to the selected path.</p>
            </div>
          </div>
          {!selectedLeak && <p className="subtle">Select a path to see factors.</p>}
          {selectedLeak && (
            <div className="leak-factors">
              <div className="leak-factors-row">
                <span>Sessions</span>
                <strong>{selectedLeak.sessions?.toLocaleString?.() || 0}</strong>
              </div>
              <div className="leak-factors-row">
                <span>Lost conversions</span>
                <strong>{selectedLeak.lost_conversions?.toFixed?.(1) || "0.0"}</strong>
              </div>
              <div className="leak-factors-row">
                <span>Est. lost revenue</span>
                <strong>{formatCurrency(selectedLeak.total_lost_revenue)}</strong>
              </div>
              <div className="leak-factor-list">
                {(selectedLeak.top_factors || []).length ? (
                  selectedLeak.top_factors.map((factor) => (
                    <div key={`${factor.factor_type}-${factor.severity}`} className="leak-factor-item">
                      <span className={`factor-badge ${factor.severity || "medium"}`}>
                        {formatFactorLabel(factor.factor_type)}
                      </span>
                      <span className="subtle">{factor.count} signals</span>
                    </div>
                  ))
                ) : (
                  <div className="subtle">No trust factors yet for this path.</div>
                )}
              </div>
              {selectedLeak.incident_ids?.length ? (
                <div className="leak-incident-links">
                  <div className="leak-panel-title">Related incidents</div>
                  <div className="leak-incident-list">
                    {selectedLeak.incident_ids.map((id) => (
                      <button
                        key={id}
                        className="btn secondary small"
                        onClick={() =>
                          navigateTo(
                            includeDemo
                              ? `/dashboard/revenue-integrity/incidents/${id}?demo=1`
                              : `/dashboard/revenue-integrity/incidents/${id}`
                          )
                        }
                      >
                        Incident #{id}
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          )}
        </aside>
      </section>
      <TourOverlay
        steps={leaksTourSteps}
        isOpen={leaksTour.open}
        onComplete={leaksTour.complete}
        onDismiss={leaksTour.dismiss}
      />
    </div>
  );
}
