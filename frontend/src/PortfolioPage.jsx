import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "./api";

const formatCurrency = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return Number(value).toLocaleString(undefined, { style: "currency", currency: "USD" });
};

const formatNumber = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return Number(value).toLocaleString();
};

const formatScore = (value) => (value === null || value === undefined ? "-" : value);

function PortfolioPage() {
  const [items, setItems] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [upgradeMessage, setUpgradeMessage] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [stackFilter, setStackFilter] = useState("");
  const [regionFilter, setRegionFilter] = useState("");
  const [exporting, setExporting] = useState(false);

  const queryString = useMemo(() => {
    const params = new URLSearchParams();
    if (statusFilter) params.set("status", statusFilter);
    if (stackFilter) params.set("stack_type", stackFilter);
    if (regionFilter) params.set("region", regionFilter);
    return params.toString();
  }, [statusFilter, stackFilter, regionFilter]);

  useEffect(() => {
    let active = true;
    const loadPortfolio = async () => {
      setLoading(true);
      setError("");
      setUpgradeMessage("");
      try {
        const summaryPath = `/api/v1/portfolio/summary${queryString ? `?${queryString}` : ""}`;
        const websitesPath = `/api/v1/portfolio/websites${queryString ? `?${queryString}` : ""}`;
        const [summaryResp, websitesResp] = await Promise.all([
          apiFetch(summaryPath, { skipReauth: true }),
          apiFetch(websitesPath, { skipReauth: true }),
        ]);
        if (!active) return;
        if (summaryResp.status === 403 || websitesResp.status === 403) {
          const payload = await (summaryResp.ok ? websitesResp.json() : summaryResp.json()).catch(() => ({}));
          setUpgradeMessage(payload?.detail || "Portfolio scorecards require a Business plan.");
          setSummary(null);
          setItems([]);
          return;
        }
        if (!summaryResp.ok) {
          const payload = await summaryResp.json().catch(() => ({}));
          throw new Error(payload?.detail || "Failed to load portfolio summary.");
        }
        if (!websitesResp.ok) {
          const payload = await websitesResp.json().catch(() => ({}));
          throw new Error(payload?.detail || "Failed to load portfolio websites.");
        }
        const summaryPayload = await summaryResp.json();
        const websitesPayload = await websitesResp.json();
        setSummary(summaryPayload.summary);
        setItems(websitesPayload);
      } catch (err) {
        if (active) {
          setError(err?.message || "Failed to load portfolio data.");
        }
      } finally {
        if (active) setLoading(false);
      }
    };
    loadPortfolio();
    return () => {
      active = false;
    };
  }, [queryString]);

  const handleExport = async (format) => {
    setExporting(true);
    setError("");
    try {
      const exportPath = `/api/v1/portfolio/export?format=${format}${queryString ? `&${queryString}` : ""}`;
      const resp = await apiFetch(exportPath, { skipReauth: true });
      if (resp.status === 403) {
        const payload = await resp.json().catch(() => ({}));
        setUpgradeMessage(payload?.detail || "Portfolio exports require an Enterprise plan.");
        return;
      }
      if (!resp.ok) {
        const payload = await resp.json().catch(() => ({}));
        throw new Error(payload?.detail || "Export failed.");
      }
      if (format === "csv") {
        const blob = await resp.blob();
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `portfolio_export_${Date.now()}.csv`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.URL.revokeObjectURL(url);
      } else {
        const payload = await resp.json();
        const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `portfolio_export_${Date.now()}.json`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.URL.revokeObjectURL(url);
      }
    } catch (err) {
      setError(err?.message || "Export failed.");
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="stack">
      <section className="card portfolio-header">
        <div>
          <h2 className="section-title">Managed Security Scorecards</h2>
          <p className="subtle">
            Portfolio view of trust health, incidents, and revenue leakage across your websites.
          </p>
        </div>
        <div className="row">
          <button className="btn secondary" onClick={() => handleExport("csv")} disabled={exporting}>
            Export CSV
          </button>
          <button className="btn secondary" onClick={() => handleExport("json")} disabled={exporting}>
            Export JSON
          </button>
        </div>
      </section>

      <section className="card portfolio-filters">
        <div className="field">
          <label>Status</label>
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">All</option>
            <option value="active">Active</option>
            <option value="paused">Paused</option>
          </select>
        </div>
        <div className="field">
          <label>Stack</label>
          <select value={stackFilter} onChange={(e) => setStackFilter(e.target.value)}>
            <option value="">All</option>
            <option value="wordpress">WordPress</option>
            <option value="shopify">Shopify</option>
            <option value="nextjs">Next.js</option>
            <option value="react_spa">React SPA</option>
            <option value="django">Django</option>
            <option value="rails">Rails</option>
            <option value="custom">Custom</option>
          </select>
        </div>
        <div className="field">
          <label>Region</label>
          <select value={regionFilter} onChange={(e) => setRegionFilter(e.target.value)}>
            <option value="">All</option>
            <option value="us">US</option>
            <option value="eu">EU</option>
          </select>
        </div>
      </section>

      {upgradeMessage && (
        <section className="card">
          <h3 className="section-title">Upgrade required</h3>
          <p className="subtle">{upgradeMessage}</p>
        </section>
      )}

      {error && (
        <section className="card">
          <p className="error-text">{error}</p>
        </section>
      )}

      {loading && (
        <section className="card">
          <p className="subtle">Loading portfolio scorecards...</p>
        </section>
      )}

      {summary && (
        <section className="card portfolio-summary">
          <div>
            <div className="muted small">Websites tracked</div>
            <strong>{summary.website_count}</strong>
          </div>
          <div>
            <div className="muted small">Avg trust score</div>
            <strong>{formatScore(summary.avg_trust_score)}</strong>
          </div>
          <div>
            <div className="muted small">Open incidents</div>
            <strong>{summary.open_incidents_total}</strong>
          </div>
          <div>
            <div className="muted small">Critical incidents</div>
            <strong>{summary.open_incidents_critical}</strong>
          </div>
          <div>
            <div className="muted small">Lost revenue (range)</div>
            <strong>{formatCurrency(summary.total_revenue_leak)}</strong>
          </div>
          {summary.range_notice && (
            <div className="portfolio-notice subtle">{summary.range_notice}</div>
          )}
        </section>
      )}

      <section className="card">
        <div className="table-wrapper">
          <table className="table">
            <thead>
              <tr>
                <th>Website</th>
                <th>Status</th>
                <th>Stack</th>
                <th>Region</th>
                <th>Trust</th>
                <th>Incidents</th>
                <th>Lost revenue (7d)</th>
              </tr>
            </thead>
            <tbody>
              {!items.length && !loading ? (
                <tr>
                  <td colSpan="7" className="subtle">No websites match your filters.</td>
                </tr>
              ) : (
                items.map((item) => (
                  <tr key={item.website_id}>
                    <td>
                      <div className="portfolio-domain">{item.domain}</div>
                      <div className="muted small">{item.display_name || "-"}</div>
                    </td>
                    <td>{item.status}</td>
                    <td>{item.stack_type || "-"}</td>
                    <td>{item.data_region || "-"}</td>
                    <td>
                      <div className="portfolio-score">
                        {formatScore(item.trust_score_current)}
                        {item.trust_verified ? <span className="badge">Verified</span> : null}
                      </div>
                      <div className="muted small">
                        {item.trust_updated_at ? new Date(item.trust_updated_at).toLocaleString() : "No data"}
                      </div>
                    </td>
                    <td>
                      <div>{formatNumber(item.incidents_open_total)}</div>
                      <div className="muted small">
                        Critical: {formatNumber(item.incidents_open_critical)}
                      </div>
                    </td>
                    <td>{formatCurrency(item.revenue_leak_7d)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

export default PortfolioPage;
