import { useEffect, useState } from "react";
import { apiFetch, ACTIVE_TENANT_KEY } from "./api";

const BRANDING_MODES = [
  { value: "your_brand", label: "APIShield branding" },
  { value: "co_brand", label: "Co-branded" },
  { value: "white_label", label: "White-label" },
];

const emptyForm = {
  is_enabled: false,
  brand_name: "",
  logo_url: "",
  primary_color: "",
  accent_color: "",
  custom_domain: "",
  badge_branding_mode: "your_brand",
};

export default function BrandingSettingsPage() {
  const [tenants, setTenants] = useState([]);
  const [activeTenant, setActiveTenant] = useState(
    localStorage.getItem(ACTIVE_TENANT_KEY) || ""
  );
  const [branding, setBranding] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [verifyState, setVerifyState] = useState({ loading: false, message: "" });

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
      setBranding(null);
      setForm(emptyForm);
      return;
    }
    localStorage.setItem(ACTIVE_TENANT_KEY, activeTenant);
    let mounted = true;
    async function loadBranding() {
      setLoading(true);
      setError("");
      try {
        const resp = await apiFetch("/api/v1/branding");
        if (!resp.ok) {
          throw new Error("Unable to load branding");
        }
        const data = await resp.json();
        if (!mounted) return;
        setBranding(data);
        setForm({
          is_enabled: Boolean(data.is_enabled),
          brand_name: data.brand_name || "",
          logo_url: data.logo_url || "",
          primary_color: data.primary_color || "",
          accent_color: data.accent_color || "",
          custom_domain: data.custom_domain || "",
          badge_branding_mode: data.badge_branding_mode || "your_brand",
        });
        setNotice("");
      } catch (err) {
        if (!mounted) return;
        setError(err.message || "Unable to load branding");
      } finally {
        if (mounted) setLoading(false);
      }
    }
    loadBranding();
    return () => {
      mounted = false;
    };
  }, [activeTenant]);

  const updateField = (key, value) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const handleSave = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const resp = await apiFetch("/api/v1/branding", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          is_enabled: form.is_enabled,
          brand_name: form.brand_name || null,
          logo_url: form.logo_url || null,
          primary_color: form.primary_color || null,
          accent_color: form.accent_color || null,
          custom_domain: form.custom_domain || null,
          badge_branding_mode: form.badge_branding_mode,
        }),
      });
      if (!resp.ok) {
        const payload = await resp.json().catch(() => ({}));
        throw new Error(payload.detail || "Unable to save branding");
      }
      const data = await resp.json();
      setBranding(data);
      setForm({
        is_enabled: Boolean(data.is_enabled),
        brand_name: data.brand_name || "",
        logo_url: data.logo_url || "",
        primary_color: data.primary_color || "",
        accent_color: data.accent_color || "",
        custom_domain: data.custom_domain || "",
        badge_branding_mode: data.badge_branding_mode || "your_brand",
      });
      if (form.badge_branding_mode !== data.badge_branding_mode || (form.is_enabled && !data.is_enabled)) {
        setNotice("Some branding options were adjusted based on your plan.");
      }
    } catch (err) {
      setError(err.message || "Unable to save branding");
    } finally {
      setSaving(false);
    }
  };

  const handleVerifyDomain = async () => {
    setVerifyState({ loading: true, message: "" });
    try {
      const resp = await apiFetch("/api/v1/branding/verify", { method: "POST" });
      if (!resp.ok) {
        const payload = await resp.json().catch(() => ({}));
        throw new Error(payload.detail || "Verification failed");
      }
      const data = await resp.json();
      setBranding(data);
      setForm((prev) => ({ ...prev, custom_domain: data.custom_domain || "" }));
      setVerifyState({ loading: false, message: "Domain verified successfully." });
    } catch (err) {
      setVerifyState({ loading: false, message: err.message || "Verification failed" });
    }
  };

  return (
    <div className="stack branding-page">
      <section className="card branding-header">
        <div>
          <h2 className="section-title">Branding & White-label</h2>
          <p className="subtle">
            Customize dashboard branding, badge appearance, and configure a custom domain.
          </p>
        </div>
        <div className="branding-tenant">
          <label className="label">Active tenant</label>
          <select
            className="select"
            value={activeTenant}
            onChange={(event) => setActiveTenant(event.target.value)}
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
        {loading ? (
          <p className="subtle">Loading branding settings…</p>
        ) : (
          <form className="branding-form" onSubmit={handleSave}>
            <div className="branding-grid">
              <div className="field">
                <label className="label">Enable custom branding</label>
                <label className="checkbox-row">
                  <input
                    type="checkbox"
                    checked={form.is_enabled}
                    onChange={(event) => updateField("is_enabled", event.target.checked)}
                  />
                  <span>Apply logo and colors in the dashboard</span>
                </label>
              </div>
              <div className="field">
                <label className="label">Brand name</label>
                <input
                  type="text"
                  value={form.brand_name}
                  onChange={(event) => updateField("brand_name", event.target.value)}
                  placeholder="Acme Security"
                />
              </div>
              <div className="field">
                <label className="label">Logo URL</label>
                <input
                  type="text"
                  value={form.logo_url}
                  onChange={(event) => updateField("logo_url", event.target.value)}
                  placeholder="https://cdn.example.com/logo.png"
                />
              </div>
              <div className="field">
                <label className="label">Primary color</label>
                <input
                  type="text"
                  value={form.primary_color}
                  onChange={(event) => updateField("primary_color", event.target.value)}
                  placeholder="#3b82f6"
                />
              </div>
              <div className="field">
                <label className="label">Accent color</label>
                <input
                  type="text"
                  value={form.accent_color}
                  onChange={(event) => updateField("accent_color", event.target.value)}
                  placeholder="#0ea5e9"
                />
              </div>
              <div className="field">
                <label className="label">Badge branding mode</label>
                <select
                  className="select"
                  value={form.badge_branding_mode}
                  onChange={(event) => updateField("badge_branding_mode", event.target.value)}
                >
                  {BRANDING_MODES.map((mode) => (
                    <option key={mode.value} value={mode.value}>
                      {mode.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label className="label">Custom domain</label>
                <input
                  type="text"
                  value={form.custom_domain}
                  onChange={(event) => updateField("custom_domain", event.target.value)}
                  placeholder="dashboard.acme.com"
                />
              </div>
            </div>
            <div className="row">
              <button className="btn primary" type="submit" disabled={saving}>
                {saving ? "Saving…" : "Save branding"}
              </button>
            </div>
            {notice && <p className="muted">{notice}</p>}
            {error && <p className="error-text">{error}</p>}
          </form>
        )}
      </section>

      {branding?.custom_domain && (
        <section className="card branding-domain">
          <div className="branding-domain-header">
            <div>
              <h3 className="section-title">Custom domain verification</h3>
              <p className="subtle">
                Add the TXT record below to verify domain ownership.
              </p>
            </div>
            <div className="branding-domain-status">
              {branding.domain_verified_at ? (
                <span className="badge pro">Verified</span>
              ) : (
                <span className="badge">Pending</span>
              )}
            </div>
          </div>
          {branding.verification_txt_name && (
            <div className="branding-dns-record">
              <div>
                <div className="muted small">TXT record name</div>
                <strong>{branding.verification_txt_name}</strong>
              </div>
              <div>
                <div className="muted small">TXT record value</div>
                <strong>{branding.verification_txt_value}</strong>
              </div>
            </div>
          )}
          <div className="row">
            <button
              className="btn secondary"
              type="button"
              onClick={handleVerifyDomain}
              disabled={verifyState.loading || Boolean(branding.domain_verified_at)}
            >
              {verifyState.loading ? "Verifying…" : "Verify domain"}
            </button>
            {verifyState.message && <span className="muted">{verifyState.message}</span>}
          </div>
        </section>
      )}
    </div>
  );
}
