const perfStore = (typeof window !== "undefined" && (window.__perfMetrics ||= [])) || [];

export const recordPerfMetric = (name, value, meta = {}) => {
  const payload = {
    name,
    value: Number.isFinite(value) ? Math.round(value * 100) / 100 : value,
    meta,
    ts: new Date().toISOString(),
  };
  perfStore.push(payload);
  if (process.env.NODE_ENV !== "production") {
    console.debug("perf.metric", payload);
  }
};

export const captureNavigationTimings = () => {
  if (typeof window === "undefined" || !window.performance) return;
  const nav = performance.getEntriesByType("navigation")[0];
  if (nav) {
    recordPerfMetric("ttfb_ms", nav.responseStart);
    recordPerfMetric("dom_content_loaded_ms", nav.domContentLoadedEventEnd);
  }
  const fcp = performance.getEntriesByName("first-contentful-paint")[0];
  if (fcp) {
    recordPerfMetric("fcp_ms", fcp.startTime);
  }
};

export const markDashboardReady = (meta = {}) => {
  if (typeof window === "undefined" || !window.performance) return;
  recordPerfMetric("dashboard_ready_ms", performance.now(), meta);
};
