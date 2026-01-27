import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "./api";

const EMPTY_DETAIL = {
  tenant: null,
  subscription: null,
  entitlements: null,
  usage: null,
  health: null,
};

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString();
}

function formatBytes(value) {
  if (!value) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = value;
  let idx = 0;
  while (size >= 1024 && idx < units.length - 1) {
    size /= 1024;
    idx += 1;
  }
  return `${size.toFixed(1)} ${units[idx]}`;
}

function AdminConsolePage() {
  const [query, setQuery] = useState("");
  const [tenants, setTenants] = useState([]);
  const [selectedTenant, setSelectedTenant] = useState(null);
  const [tenantDetail, setTenantDetail] = useState(EMPTY_DETAIL);
  const [incidents, setIncidents] = useState([]);
  const [loading, setLoading] = useState(false);
  const [accessDenied, setAccessDenied] = useState(false);
  const [supportReason, setSupportReason] = useState("");
  const [supportToken, setSupportToken] = useState(null);
  const [supportExpires, setSupportExpires] = useState(null);
  const [supportSnapshot, setSupportSnapshot] = useState(null);
  const [supportError, setSupportError] = useState(null);

  const hasSelection = Boolean(selectedTenant);

  const searchTenants = async (q) => {
    setLoading(true);
    setAccessDenied(false);
    try {
      const resp = await apiFetch(`/api/v1/admin/tenants?query=${encodeURIComponent(q || "")}`);
      if (resp.status === 403) {
        setAccessDenied(true);
        setTenants([]);
        return;
      }
      const data = await resp.json();
      setTenants(data || []);
    } catch (err) {
      console.error("admin tenant search failed", err);
    } finally {
      setLoading(false);
    }
  };

  const loadTenantDetail = async (tenant) => {
    if (!tenant) return;
    setLoading(true);
    setSupportSnapshot(null);
    setSupportToken(null);
    setSupportExpires(null);
    try {
      const [detailResp, incidentsResp] = await Promise.all([
        apiFetch(`/api/v1/admin/tenants/${tenant.id}`),
        apiFetch(`/api/v1/admin/tenants/${tenant.id}/incidents?status=open`),
      ]);
      if (!detailResp.ok) {
        throw new Error("Failed to load tenant details");
      }
      const detailData = await detailResp.json();
      const incidentData = incidentsResp.ok ? await incidentsResp.json() : [];
      setTenantDetail(detailData || EMPTY_DETAIL);
      setIncidents(incidentData || []);
    } catch (err) {
      console.error("admin tenant detail failed", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    searchTenants("");
  }, []);

  const handleSelect = (tenant) => {
    setSelectedTenant(tenant);
    loadTenantDetail(tenant);
  };

  const supportFetch = async (path) => {
    if (!supportToken || !selectedTenant) return null;
    const headers = {
      Authorization: `Bearer ${supportToken}`,
      "X-Tenant-ID": String(selectedTenant.id),
    };
    const resp = await apiFetch(path, { headers, skipReauth: true });
    if (!resp.ok) {
      return null;
    }
    return resp.json();
  };

  const refreshSupportSnapshot = async () => {
    if (!supportToken || !selectedTenant) return;
    setSupportError(null);
    try {
      const [settings, entitlements, websites, incidentList] = await Promise.all([
        supportFetch("/api/v1/settings"),
        supportFetch("/api/v1/entitlements"),
        supportFetch("/api/v1/websites"),
        supportFetch("/api/v1/incidents"),
      ]);
      setSupportSnapshot({
        settings,
        entitlements,
        websites,
        incidents: incidentList,
      });
    } catch (err) {
      console.error("support snapshot failed", err);
      setSupportError("Unable to load support snapshot.");
    }
  };

  const startSupportView = async () => {
    if (!selectedTenant) return;
    setSupportError(null);
    try {
      const resp = await apiFetch("/api/v1/admin/support/view-as", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tenant_id: selectedTenant.id, reason: supportReason }),
      });
      if (!resp.ok) {
        const errorBody = await resp.json().catch(() => ({}));
        setSupportError(errorBody.detail || "Support session failed.");
        return;
      }
      const data = await resp.json();
      setSupportToken(data.support_token);
      setSupportExpires(data.expires_at);
      await refreshSupportSnapshot();
    } catch (err) {
      console.error("support view-as failed", err);
      setSupportError("Support session failed.");
    }
  };

  const entitlementSummary = useMemo(() => {
    const ent = tenantDetail.entitlements || {};
    const features = Object.entries(ent.features || {})
      .filter(([, enabled]) => enabled)
      .map(([key]) => key);
    return features.length ? features.join(", ") : "No enabled features";
  }, [tenantDetail.entitlements]);

  if (accessDenied) {
    return (
      <section className="card">
        <h2 className="section-title">Admin Console</h2>
        <p>Access denied. Platform admin privileges required.</p>
      </section>
    );
  }

  return (
    <section className="card">
      <div className="row space-between align-center">
        <div>
          <h2 className="section-title">Admin Console</h2>
          <p className="muted">
            Tenant lookup, usage, health, and support view with audit trail.
          </p>
        </div>
        <div className="row">
          <input
            className="input"
            placeholder="Search tenant name, slug, or id"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <button className="btn secondary" onClick={() => searchTenants(query)}>
            Search
          </button>
        </div>
      </div>

      {loading && <p className="muted">Loading…</p>}

      <div className="admin-grid">
        <div className="admin-list">
          <h3>Tenants</h3>
          {tenants.length === 0 ? (
            <p className="muted">No tenants found.</p>
          ) : (
            <ul className="list">
              {tenants.map((tenant) => (
                <li key={tenant.id}>
                  <button
                    className={`btn tertiary ${selectedTenant?.id === tenant.id ? "active" : ""}`}
                    onClick={() => handleSelect(tenant)}
                  >
                    <div>
                      <strong>{tenant.name}</strong>
                      <div className="muted small">#{tenant.id} · {tenant.slug} · {tenant.data_region || "us"}</div>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="admin-detail">
          {!hasSelection ? (
            <p className="muted">Select a tenant to view details.</p>
          ) : (
            <>
              <h3>Tenant Detail</h3>
              <div className="admin-section">
                <h4>Overview</h4>
                <p><strong>Name:</strong> {tenantDetail.tenant?.name}</p>
                <p><strong>Slug:</strong> {tenantDetail.tenant?.slug}</p>
                <p><strong>Region:</strong> {tenantDetail.tenant?.data_region || "us"}</p>
                <p><strong>Created:</strong> {formatDate(tenantDetail.tenant?.created_at)}</p>
              </div>

              <div className="admin-section">
                <h4>Subscription</h4>
                <p><strong>Plan:</strong> {tenantDetail.subscription?.plan_name || "—"}</p>
                <p><strong>Status:</strong> {tenantDetail.subscription?.status || "—"}</p>
                <p>
                  <strong>Period End:</strong>{" "}
                  {formatDate(tenantDetail.subscription?.current_period_end)}
                </p>
              </div>

              <div className="admin-section">
                <h4>Usage</h4>
                <p><strong>Events:</strong> {tenantDetail.usage?.events_ingested || 0}</p>
                <p><strong>Storage:</strong> {formatBytes(tenantDetail.usage?.storage_bytes || 0)}</p>
                <p><strong>Websites:</strong> {tenantDetail.usage?.websites_count || 0}</p>
                <p><strong>Members:</strong> {tenantDetail.usage?.members_count || 0}</p>
              </div>

              <div className="admin-section">
                <h4>Entitlements</h4>
                <p>{entitlementSummary}</p>
              </div>

              <div className="admin-section">
                <h4>Health</h4>
                <p><strong>Last ingest:</strong> {formatDate(tenantDetail.health?.last_ingest_at)}</p>
                <p><strong>Ingest 1h:</strong> {tenantDetail.health?.ingest_events_1h || 0}</p>
                <p><strong>Ingest 24h:</strong> {tenantDetail.health?.ingest_events_24h || 0}</p>
                <p>
                  <strong>Ingest success rate 1h:</strong>{" "}
                  {tenantDetail.health?.ingest_success_rate_1h != null
                    ? `${(tenantDetail.health.ingest_success_rate_1h * 100).toFixed(1)}%`
                    : "—"}
                </p>
                <p><strong>Rate limit hits 1h:</strong> {tenantDetail.health?.ingest_rate_limit_1h || 0}</p>
                <p><strong>Security events 1h:</strong> {tenantDetail.health?.security_events_1h || 0}</p>
                <p><strong>Export failures 7d:</strong> {tenantDetail.health?.export_failures_7d || 0}</p>
                <p><strong>Retention failures 7d:</strong> {tenantDetail.health?.retention_failures_7d || 0}</p>
                <p><strong>Notification failures 24h:</strong> {tenantDetail.health?.notification_failures_24h || 0}</p>
              </div>

              <div className="admin-section">
                <h4>Open Incidents</h4>
                {incidents.length === 0 ? (
                  <p className="muted">No open incidents.</p>
                ) : (
                  <ul className="list">
                    {incidents.map((incident) => (
                      <li key={incident.id}>
                        <strong>{incident.title}</strong> · {incident.severity} · {formatDate(incident.last_seen_at)}
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div className="admin-section">
                <h4>Support View (Read-only)</h4>
                <p className="muted">
                  Generates a short-lived support token for safe read-only diagnostics.
                </p>
                <div className="row">
                  <input
                    className="input"
                    placeholder="Reason for access"
                    value={supportReason}
                    onChange={(e) => setSupportReason(e.target.value)}
                  />
                  <button className="btn secondary" onClick={startSupportView}>
                    Start Support View
                  </button>
                </div>
                {supportError && <p className="error">{supportError}</p>}
                {supportToken && (
                  <div className="support-panel">
                    <p>
                      <strong>Support token expires:</strong> {formatDate(supportExpires)}
                    </p>
                    <button className="btn tertiary" onClick={refreshSupportSnapshot}>
                      Refresh Support Snapshot
                    </button>
                    {supportSnapshot ? (
                      <div className="support-snapshot">
                        <div>
                          <h5>Settings</h5>
                          <pre>{JSON.stringify(supportSnapshot.settings, null, 2)}</pre>
                        </div>
                        <div>
                          <h5>Entitlements</h5>
                          <pre>{JSON.stringify(supportSnapshot.entitlements, null, 2)}</pre>
                        </div>
                        <div>
                          <h5>Websites</h5>
                          <pre>{JSON.stringify(supportSnapshot.websites, null, 2)}</pre>
                        </div>
                        <div>
                          <h5>Incidents</h5>
                          <pre>{JSON.stringify(supportSnapshot.incidents, null, 2)}</pre>
                        </div>
                      </div>
                    ) : (
                      <p className="muted">Support snapshot not loaded yet.</p>
                    )}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  );
}

export default AdminConsolePage;
