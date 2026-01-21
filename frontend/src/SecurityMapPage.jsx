import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch, ACTIVE_TENANT_KEY } from "./api";
import GeoMapView from "./GeoMapView";

const TIME_RANGES = [
  { value: "24h", label: "Last 24 hours", days: 1 },
  { value: "7d", label: "Last 7 days", days: 7 },
  { value: "30d", label: "Last 30 days", days: 30 },
];

const GRANULARITY_LEVELS = { country: 0, city: 1, asn: 2 };
const LIMITED_CATEGORIES = ["login", "integrity"];
const UPGRADE_PATH = "/billing";

const CATEGORY_OPTIONS = [
  { value: "login", label: "Logins" },
  { value: "threat", label: "Threats" },
  { value: "integrity", label: "Integrity" },
  { value: "bot", label: "Bots" },
  { value: "anomaly", label: "Anomalies" },
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
  if (!value) return CATEGORY_OPTIONS[0].value;
  const match = CATEGORY_OPTIONS.find((option) => option.value === value);
  return match ? match.value : CATEGORY_OPTIONS[0].value;
};

const parseSeverityParam = (value) => {
  if (!value) return "";
  const match = SEVERITY_OPTIONS.find((option) => option.value === value);
  return match ? match.value : "";
};

const parseGranularity = (value) => {
  if (!value) return null;
  const normalized = String(value).toLowerCase();
  return GRANULARITY_LEVELS[normalized] != null ? normalized : null;
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
  };
};

const isSameInstant = (left, right) =>
  isValidDate(left) && isValidDate(right) && left.getTime() === right.getTime();

const escapeCsv = (value) => {
  if (value == null) return "";
  const text = String(value);
  if (/[",\n]/.test(text)) {
    return `"${text.replace(/"/g, "\"\"")}"`;
  }
  return text;
};

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
  const [geoFeatureEnabled, setGeoFeatureEnabled] = useState(null);
  const [geoGranularity, setGeoGranularity] = useState(null);
  const [geoHistoryDays, setGeoHistoryDays] = useState(null);
  const [timeClampNotice, setTimeClampNotice] = useState("");
  const [shareStatus, setShareStatus] = useState("");
  const [summary, setSummary] = useState([]);
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [error, setError] = useState("");
  const [planLimited, setPlanLimited] = useState(false);
  const [viewMode, setViewMode] = useState("map");
  const [debouncedFilters, setDebouncedFilters] = useState({
    activeTenant,
    websiteId,
    envId,
    category,
    severity,
    from: fromTs,
    to: toTs,
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

  const geoEnabled = geoFeatureEnabled !== false;
  const resolvedGranularity = geoGranularity || "city";
  const granularityRank = GRANULARITY_LEVELS[resolvedGranularity] ?? GRANULARITY_LEVELS.city;
  const hasCityGranularity = geoEnabled && granularityRank >= GRANULARITY_LEVELS.city;
  const hasAsnGranularity = geoEnabled && granularityRank >= GRANULARITY_LEVELS.asn;
  const hasFullFilters = geoEnabled && hasAsnGranularity;
  const canExportCsv = geoEnabled && hasAsnGranularity;
  const allowedCategoryValues = useMemo(
    () =>
      hasFullFilters
        ? CATEGORY_OPTIONS.map((option) => option.value)
        : LIMITED_CATEGORIES,
    [hasFullFilters]
  );
  const hasHistoryLimit = useMemo(
    () => Boolean(geoHistoryDays && TIME_RANGES.some((option) => option.days > geoHistoryDays)),
    [geoHistoryDays]
  );
  const mapPlanLimited = planLimited || !hasCityGranularity;
  const showUpgradeCard =
    geoEnabled && (mapPlanLimited || !hasAsnGranularity);

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

  const updateTimeWindow = useCallback((nextFrom, nextTo) => {
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
  }, [geoHistoryDays]);

  const handleRangeChange = (event) => {
    const selected = TIME_RANGES.find(
      (option) => option.value === event.target.value
    );
    if (!selected) return;
    if (geoHistoryDays && selected.days > geoHistoryDays) return;
    const nextWindow = buildTimeWindow(selected.days, new Date());
    updateTimeWindow(nextWindow.from, nextWindow.to);
  };

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

  const handleUpgrade = () => {
    window.location.assign(UPGRADE_PATH);
  };

  const handleExportCsv = () => {
    if (!canExportCsv) return;
    const headers = [
      "count",
      "country_code",
      "region",
      "city",
      "latitude",
      "longitude",
      "asn_number",
      "asn_org",
      "is_datacenter",
    ];
    const rows = (summary || []).map((point) =>
      [
        point.count,
        point.country_code,
        point.region,
        point.city,
        point.latitude,
        point.longitude,
        point.asn_number,
        point.asn_org,
        point.is_datacenter,
      ]
        .map(escapeCsv)
        .join(",")
    );
    const csv = [headers.join(","), ...rows].join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const link = document.createElement("a");
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    link.href = URL.createObjectURL(blob);
    link.download = `geo-map-${stamp}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(link.href);
  };

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
        const granularityValue = parseGranularity(limits.geo_granularity);
        setGeoFeatureEnabled(featureEnabled);
        setGeoGranularity(granularityValue);
        setGeoHistoryDays(Number.isFinite(limitValue) && limitValue > 0 ? limitValue : null);
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
  }, [geoHistoryDays, updateTimeWindow]);

  useEffect(() => {
    if (!hasCityGranularity && viewMode === "map") {
      setViewMode("list");
    }
  }, [hasCityGranularity, viewMode]);

  useEffect(() => {
    if (!allowedCategoryValues.includes(category)) {
      setCategory(allowedCategoryValues[0] || CATEGORY_OPTIONS[0].value);
    }
  }, [allowedCategoryValues, category]);

  useEffect(() => {
    if (!hasFullFilters && severity) {
      setSeverity("");
    }
  }, [hasFullFilters, severity]);

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
      });
    }, 300);
    return () => clearTimeout(handle);
  }, [activeTenant, websiteId, envId, category, severity, fromTs, toTs]);

  useEffect(() => {
    if (!isValidDate(fromTs) || !isValidDate(toTs)) return;
    const params = new URLSearchParams();
    params.set("from", fromTs.toISOString());
    params.set("to", toTs.toISOString());
    if (websiteId) params.set("website_id", websiteId);
    if (envId) params.set("env_id", envId);
    if (category) params.set("category", category);
    if (severity) params.set("severity", severity);
    const nextUrl = `${window.location.pathname}?${params.toString()}${window.location.hash || ""}`;
    window.history.replaceState({}, "", nextUrl);
  }, [fromTs, toTs, websiteId, envId, category, severity]);

  const timeWindow = useMemo(() => {
    if (
      !isValidDate(debouncedFilters.from) ||
      !isValidDate(debouncedFilters.to)
    ) {
      return buildTimeWindow(TIME_RANGES[0].days, new Date());
    }
    return { from: debouncedFilters.from, to: debouncedFilters.to };
  }, [debouncedFilters.from, debouncedFilters.to]);

  const buildEventsLink = useCallback(
    ({ ipHash, countryCode } = {}) => {
      if (!isValidDate(timeWindow.from) || !isValidDate(timeWindow.to)) {
        return "/dashboard/security/events";
      }
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
      if (ipHash) params.set("ip_hash", ipHash);
      if (countryCode) params.set("country_code", countryCode);
      return `/dashboard/security/events?${params.toString()}`;
    },
    [debouncedFilters, timeWindow.from, timeWindow.to]
  );

  useEffect(() => {
    if (!geoEnabled || !debouncedFilters.activeTenant) return;
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
  }, [debouncedFilters, timeWindow, geoEnabled]);

  useEffect(() => {
    setDrilldownOpen(false);
    setDrilldownSelection(null);
    setDrilldownData(null);
    setDrilldownError("");
  }, [activeTenant]);

  useEffect(() => {
    if (
      !geoEnabled ||
      !drilldownOpen ||
      !drilldownSelection ||
      !debouncedFilters.activeTenant
    ) {
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
  }, [drilldownOpen, drilldownSelection, debouncedFilters, timeWindow, geoEnabled]);

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

  const upgradeItems = useMemo(() => {
    if (!geoEnabled) return [];
    const items = [];
    if (mapPlanLimited) {
      items.push("City-level map markers");
    }
    if (!hasAsnGranularity) {
      items.push("ASN attribution and IP hash breakdown");
      items.push("Full categories and severity filters");
      items.push("CSV export");
    }
    return items;
  }, [geoEnabled, mapPlanLimited, hasAsnGranularity]);

  const drilldownUpgradeMessage = useMemo(() => {
    if (!geoEnabled) return "";
    if (mapPlanLimited) {
      return "Upgrade to see city-level, ASN, and IP hash detail.";
    }
    if (!hasAsnGranularity) {
      return "Upgrade to see ASN-level attribution and IP hash detail.";
    }
    return "";
  }, [geoEnabled, mapPlanLimited, hasAsnGranularity]);

  if (geoFeatureEnabled === false) {
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

        <section className="card map-locked">
          <div className="map-locked-content">
            <div>
              <div className="map-locked-kicker">Upgrade required</div>
              <h3 className="section-title">Geo Map is a Pro feature</h3>
              <p className="subtle">
                Unlock advanced geo insights, attribution, and export-ready reports.
              </p>
            </div>
            <div className="map-locked-preview">
              <div className="map-locked-item">City-level activity clusters</div>
              <div className="map-locked-item">ASN attribution and IP hash breakdowns</div>
              <div className="map-locked-item">CSV export for security reviews</div>
            </div>
            <div className="map-locked-actions">
              <button className="btn primary" onClick={handleUpgrade}>
                Upgrade
              </button>
              <span className="help">Takes you to billing.</span>
            </div>
          </div>
        </section>
      </div>
    );
  }

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
            <label className="label">
              Time range{" "}
              {hasHistoryLimit && (
                <span className="badge pro" title="Upgrade to unlock longer history.">
                  Pro
                </span>
              )}
            </label>
            <select
              className="select"
              value={rangeValue}
              onChange={handleRangeChange}
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
            <label className="label">
              Category{" "}
              {!hasFullFilters && (
                <span className="badge pro" title="Upgrade to unlock all categories.">
                  Pro
                </span>
              )}
            </label>
            <select
              className="select"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              title={
                !hasFullFilters ? "Upgrade to unlock all categories." : undefined
              }
            >
              {CATEGORY_OPTIONS.map((option) => {
                const isAllowed = allowedCategoryValues.includes(option.value);
                return (
                  <option
                    key={option.value}
                    value={option.value}
                    disabled={!isAllowed}
                  >
                    {isAllowed ? option.label : `${option.label} (Pro)`}
                  </option>
                );
              })}
            </select>
            {!hasFullFilters && (
              <div className="help">Upgrade to unlock more categories.</div>
            )}
          </div>
          <div className="field">
            <label className="label">
              Severity{" "}
              {!hasFullFilters && (
                <span className="badge pro" title="Upgrade to unlock severity filters.">
                  Pro
                </span>
              )}
            </label>
            <select
              className="select"
              value={severity}
              onChange={(e) => setSeverity(e.target.value)}
              disabled={!hasFullFilters}
              title={
                !hasFullFilters ? "Upgrade to unlock severity filters." : undefined
              }
            >
              {SEVERITY_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            {!hasFullFilters && (
              <div className="help">Severity filters are available on Pro.</div>
            )}
          </div>
        </div>
        <div className="row">
          <button className="btn secondary" onClick={handleShare}>
            Share
          </button>
          <button
            className="btn secondary"
            onClick={handleExportCsv}
            disabled={!canExportCsv}
            title={!canExportCsv ? "Upgrade to export CSV." : "Export CSV"}
          >
            Export CSV
          </button>
          {!canExportCsv && (
            <span className="badge pro" title="Upgrade to export CSV.">
              Pro
            </span>
          )}
          {shareStatus && <span className="help">{shareStatus}</span>}
        </div>
      </section>

      {showUpgradeCard && (
        <section className="card map-upgrade">
          <div className="map-upgrade-header">
            <strong>Pro features available</strong>
            <button className="btn primary" onClick={handleUpgrade}>
              Upgrade
            </button>
          </div>
          {upgradeItems.length ? (
            <ul className="map-upgrade-list">
              {upgradeItems.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : (
            <p className="subtle">Unlock additional geo insights.</p>
          )}
        </section>
      )}

      <section className="map-grid">
        <div className="card map-panel">
          <div className="map-panel-header">
            <div>
              <h3 className="section-title">
                Map canvas{" "}
                {!hasCityGranularity && (
                  <span
                    className="badge pro"
                    title="Upgrade to see city-level map markers."
                  >
                    Pro
                  </span>
                )}
              </h3>
              <p className="subtle">Clustered activity view based on geo aggregates.</p>
            </div>
            <div className="map-view-toggle">
              <button
                className={`btn secondary ${viewMode === "map" ? "active" : ""}`}
                onClick={() => setViewMode("map")}
                disabled={!hasCityGranularity}
                title={
                  !hasCityGranularity
                    ? "Upgrade to see city-level map markers."
                    : undefined
                }
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

          {viewMode === "map" && hasCityGranularity ? (
            <GeoMapView
              points={summary}
              category={category}
              loading={loadingSummary}
              error={error}
              planLimited={mapPlanLimited}
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

              {drilldownUpgradeMessage && (
                <div
                  className="map-drilldown-upgrade"
                  title={drilldownUpgradeMessage}
                >
                  {drilldownUpgradeMessage}
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
                    <div className="map-drilldown-section-title">
                      Top cities{" "}
                      {mapPlanLimited && (
                        <span
                          className="badge pro"
                          title="Upgrade to see city-level attribution."
                        >
                          Pro
                        </span>
                      )}
                    </div>
                    {mapPlanLimited ? (
                      <div
                        className="map-drilldown-empty"
                        title="Upgrade to see city-level attribution."
                      >
                        Upgrade to see city-level detail.
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
                    <div className="map-drilldown-section-title">
                      Top ASNs{" "}
                      {!hasAsnGranularity && (
                        <span
                          className="badge pro"
                          title="Upgrade to see ASN-level attribution."
                        >
                          Pro
                        </span>
                      )}
                    </div>
                    {!hasAsnGranularity ? (
                      <div
                        className="map-drilldown-empty"
                        title="Upgrade to see ASN-level attribution."
                      >
                        Upgrade to see ASN-level attribution.
                      </div>
                    ) : drilldownData.asns?.length ? (
                      <div className="map-drilldown-list">
                        {drilldownData.asns.slice(0, 10).map((item, idx) => (
                          <div key={`${item.asn_number}-${idx}`} className="map-drilldown-row">
                            <span>
                              {item.asn_number ? `AS${item.asn_number}` : "ASN"}
                              {item.asn_org ? ` - ${item.asn_org}` : ""}
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
                    <div className="map-drilldown-section-title">
                      Top IP hashes{" "}
                      {!hasAsnGranularity && (
                        <span
                          className="badge pro"
                          title="Upgrade to see IP hash breakdown."
                        >
                          Pro
                        </span>
                      )}
                    </div>
                    {!hasAsnGranularity ? (
                      <div
                        className="map-drilldown-empty"
                        title="Upgrade to see IP hash breakdown."
                      >
                        Upgrade to see IP hash breakdown.
                      </div>
                      ) : drilldownData.ip_hashes?.length ? (
                        <div className="map-drilldown-list">
                          {drilldownData.ip_hashes.slice(0, 10).map((item) => (
                            <div key={item.ip_hash} className="map-drilldown-row">
                              <span title={item.ip_hash}>{truncateHash(item.ip_hash)}</span>
                              <div className="map-drilldown-row-actions">
                                <span>{formatCount(item.count)}</span>
                                <button
                                  className="btn secondary small"
                                  onClick={() =>
                                    navigateTo(buildEventsLink({ ipHash: item.ip_hash }))
                                  }
                                >
                                  View events
                                </button>
                              </div>
                            </div>
                          ))}
                        </div>
                    ) : (
                      <div className="map-drilldown-empty">No IP hash data.</div>
                    )}
                  </div>

                  <div className="map-drilldown-section">
                    <div className="map-drilldown-section-title">Top paths</div>
                    {drilldownData.paths?.length ? (
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
                      <button
                        className="btn secondary small"
                        onClick={() =>
                          navigateTo(
                            buildEventsLink({
                              countryCode:
                                drilldownSelection?.type === "country"
                                  ? drilldownSelection.countryCode
                                  : null,
                            })
                          )
                        }
                      >
                        View events
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
