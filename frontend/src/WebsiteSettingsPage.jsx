import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch, ACTIVE_TENANT_KEY } from "./api";

const STACK_OPTIONS = [
  { value: "wordpress", label: "WordPress" },
  { value: "shopify", label: "Shopify" },
  { value: "nextjs", label: "Next.js" },
  { value: "react_spa", label: "React SPA" },
  { value: "laravel", label: "Laravel" },
  { value: "django", label: "Django" },
  { value: "rails", label: "Rails" },
  { value: "custom", label: "Custom" },
];

const formatPercent = (value) => {
  if (value == null || Number.isNaN(value)) return "--";
  return `${Math.round(value * 100)}%`;
};

const formatStackLabel = (value) => {
  const option = STACK_OPTIONS.find((item) => item.value === value);
  return option ? option.label : value || "--";
};

export default function WebsiteSettingsPage({ websiteId }) {
  const [tenants, setTenants] = useState([]);
  const [activeTenant, setActiveTenant] = useState(
    localStorage.getItem(ACTIVE_TENANT_KEY) || ""
  );
  const [websites, setWebsites] = useState([]);
  const [selectedWebsiteId, setSelectedWebsiteId] = useState(websiteId || "");
  const [profile, setProfile] = useState(null);
  const [stackChoice, setStackChoice] = useState("custom");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

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
      setSelectedWebsiteId("");
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
        if (!selectedWebsiteId && data.length) {
          const first = data[0];
          setSelectedWebsiteId(String(first.id));
          navigateTo(`/dashboard/websites/${first.id}/settings`);
        }
      } catch (err) {
        if (!mounted) return;
        setWebsites([]);
        setSelectedWebsiteId("");
      }
    }
    loadWebsites();
    return () => {
      mounted = false;
    };
  }, [activeTenant, navigateTo, selectedWebsiteId]);

  useEffect(() => {
    if (!selectedWebsiteId) {
      setProfile(null);
      return;
    }
    let mounted = true;
    async function loadProfile() {
      setLoading(true);
      setError("");
      try {
        const resp = await apiFetch(`/api/v1/websites/${selectedWebsiteId}/stack`);
        if (!resp.ok) {
          throw new Error("Unable to load stack profile");
        }
        const data = await resp.json();
        if (!mounted) return;
        setProfile(data);
        setStackChoice(data.stack_type || "custom");
      } catch (err) {
        if (!mounted) return;
        setProfile(null);
        setError(err.message || "Unable to load stack profile");
      } finally {
        if (mounted) setLoading(false);
      }
    }
    loadProfile();
    return () => {
      mounted = false;
    };
  }, [selectedWebsiteId]);

  const handleWebsiteChange = (value) => {
    setSelectedWebsiteId(value);
    if (value) {
      navigateTo(`/dashboard/websites/${value}/settings`);
    }
  };

  const handleOverrideSave = async () => {
    if (!selectedWebsiteId) return;
    setSaving(true);
    setError("");
    try {
      const resp = await apiFetch(`/api/v1/websites/${selectedWebsiteId}/stack`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ stack_type: stackChoice }),
      });
      if (!resp.ok) {
        throw new Error("Unable to update stack profile");
      }
      const data = await resp.json();
      setProfile(data);
    } catch (err) {
      setError(err.message || "Unable to update stack profile");
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    if (!selectedWebsiteId) return;
    setSaving(true);
    setError("");
    try {
      const resp = await apiFetch(`/api/v1/websites/${selectedWebsiteId}/stack`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ manual_override: false }),
      });
      if (!resp.ok) {
        throw new Error("Unable to reset override");
      }
      const data = await resp.json();
      setProfile(data);
      setStackChoice(data.stack_type || "custom");
    } catch (err) {
      setError(err.message || "Unable to reset override");
    } finally {
      setSaving(false);
    }
  };

  const signalEntries = useMemo(() => {
    if (!profile || !profile.detected_signals_json) return [];
    const hints = profile.detected_signals_json.hints || {};
    return Object.entries(hints).filter(([, value]) => value);
  }, [profile]);

  return (
    <div className="stack">
      <section className="card website-settings-header">
        <div>
          <h2 className="section-title">Website Stack Profile</h2>
          <p className="subtle">
            Detect stack framework hints and override when remediation requires it.
          </p>
        </div>
        <div className="website-settings-tenant">
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

      <section className="card website-settings-controls">
        <div className="controls-grid">
          <div className="field">
            <label className="label">Website</label>
            <select
              className="select"
              value={selectedWebsiteId}
              onChange={(e) => handleWebsiteChange(e.target.value)}
            >
              <option value="">Select website</option>
              {websites.map((site) => (
                <option key={site.id} value={site.id}>
                  {site.display_name || site.domain}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label className="label">Detected stack</label>
            <div className="stack-inline">
              <strong>{formatStackLabel(profile?.stack_type)}</strong>
              <span className="subtle">
                Confidence {formatPercent(profile?.confidence)}
              </span>
            </div>
            {profile?.manual_override && (
              <span className="badge pro">Manual override</span>
            )}
          </div>
        </div>
      </section>

      <section className="card">
        <div className="stack-override-grid">
          <div>
            <h3 className="section-title">Override stack</h3>
            <p className="subtle">
              Use this when the detector is wrong or when you need stack-specific guidance.
            </p>
            <div className="field">
              <label className="label">Stack type</label>
              <select
                className="select"
                value={stackChoice}
                onChange={(e) => setStackChoice(e.target.value)}
              >
                {STACK_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="row">
              <button
                className="btn primary"
                onClick={handleOverrideSave}
                disabled={saving || !selectedWebsiteId}
              >
                Save override
              </button>
              <button
                className="btn secondary"
                onClick={handleReset}
                disabled={saving || !selectedWebsiteId}
              >
                Use auto-detect
              </button>
            </div>
            {saving && <p className="subtle">Saving changes...</p>}
            {error && <p className="error-text">{error}</p>}
          </div>
          <div className="stack-signal-panel">
            <h3 className="section-title">Detection signals</h3>
            {loading && <p className="subtle">Loading profile...</p>}
            {!loading && profile && signalEntries.length === 0 && (
              <p className="subtle">No stack hints detected yet.</p>
            )}
            {!loading && signalEntries.length > 0 && (
              <ul className="stack-signal-list">
                {signalEntries.map(([key]) => (
                  <li key={key}>{key.replace(/_/g, " ")}</li>
                ))}
              </ul>
            )}
            {!loading && profile?.detected_signals_json && (
              <pre className="stack-signal-json">
                {JSON.stringify(profile.detected_signals_json, null, 2)}
              </pre>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
