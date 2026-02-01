import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch, ACTIVE_TENANT_KEY, API_BASE } from "./api";

const CATEGORY_LABELS = {
  cms: "CMS",
  ecommerce: "E-commerce",
  frontend: "Frontend",
  security: "Security",
  observability: "Observability",
  other: "Other",
};

const normalize = (value) => String(value || "").toLowerCase();

const collectUtm = () => {
  const params = new URLSearchParams(window.location.search);
  const utm = {};
  ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"].forEach((key) => {
    const value = params.get(key);
    if (value) utm[key] = value;
  });
  return utm;
};

const CopyButton = ({ payload, onCopy }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(payload);
        setCopied(true);
        if (onCopy) onCopy();
        setTimeout(() => setCopied(false), 1500);
      }
    } catch (err) {
      // ignore
    }
  }, [payload, onCopy]);

  return (
    <button className="btn secondary small" onClick={handleCopy}>
      {copied ? "Copied" : "Copy config"}
    </button>
  );
};

export function IntegrationsDirectory({ publicMode = false }) {
  const [listings, setListings] = useState([]);
  const [websites, setWebsites] = useState([]);
  const [selectedWebsiteId, setSelectedWebsiteId] = useState("");
  const [category, setCategory] = useState("all");
  const [search, setSearch] = useState("");
  const [recommendedOnly, setRecommendedOnly] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const activeTenant = localStorage.getItem(ACTIVE_TENANT_KEY) || "";
  const utm = useMemo(() => collectUtm(), []);

  const loadWebsites = useCallback(async () => {
    if (publicMode || !activeTenant) return;
    try {
      const resp = await apiFetch("/api/v1/websites");
      if (!resp.ok) throw new Error("Unable to load websites");
      const data = await resp.json();
      setWebsites(data || []);
      if (data?.length && !selectedWebsiteId) {
        setSelectedWebsiteId(String(data[0].id));
      }
    } catch (err) {
      setWebsites([]);
    }
  }, [publicMode, activeTenant, selectedWebsiteId]);

  const loadListings = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      let endpoint = `${API_BASE}/public/integrations`;
      if (!publicMode) {
        const params = new URLSearchParams();
        if (selectedWebsiteId) params.set("website_id", selectedWebsiteId);
        if (recommendedOnly) params.set("recommended_only", "true");
        if (category && category !== "all") params.set("category", category);
        endpoint = `/api/v1/integrations/directory${params.toString() ? `?${params.toString()}` : ""}`;
      }
      const resp = publicMode ? await fetch(endpoint) : await apiFetch(endpoint);
      if (!resp.ok) throw new Error("Unable to load integrations");
      const data = await resp.json();
      setListings(data || []);
    } catch (err) {
      setError(err.message || "Unable to load integrations");
      setListings([]);
    } finally {
      setLoading(false);
    }
  }, [publicMode, selectedWebsiteId, recommendedOnly, category]);

  const logInstallEvent = useCallback(
    async (listing, method) => {
      if (publicMode) return;
      try {
        await apiFetch("/api/v1/integrations/install-events", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            integration_key: listing.key,
            website_id: selectedWebsiteId ? Number(selectedWebsiteId) : null,
            method,
            metadata: { source: "directory", ...utm },
          }),
          skipReauth: true,
        });
      } catch (err) {
        // ignore telemetry failures
      }
    },
    [publicMode, selectedWebsiteId, utm]
  );

  useEffect(() => {
    loadWebsites();
  }, [loadWebsites]);

  useEffect(() => {
    loadListings();
  }, [loadListings]);

  const filtered = useMemo(() => {
    const query = normalize(search);
    if (!query) return listings;
    return listings.filter((item) => {
      const haystack = [item.name, item.description, item.category]
        .filter(Boolean)
        .map(normalize)
        .join(" ");
      return haystack.includes(query);
    });
  }, [listings, search]);

  const categories = useMemo(() => {
    const set = new Set(listings.map((item) => item.category));
    return ["all", ...Array.from(set).sort()];
  }, [listings]);

  return (
    <div className="stack integrations-page">
      <section className="card integrations-header">
        <div>
          <h2 className="section-title">Integrations</h2>
          <p className="subtle">
            Browse install guides, copy presets, and track what gets deployed.
          </p>
        </div>
        <div className="integrations-controls">
          {!publicMode && (
            <div className="integrations-select">
              <label className="label">Website</label>
              <select
                className="select"
                value={selectedWebsiteId}
                onChange={(event) => setSelectedWebsiteId(event.target.value)}
              >
                {websites.length === 0 && <option value="">No websites yet</option>}
                {websites.map((site) => (
                  <option key={site.id} value={site.id}>
                    {site.display_name || site.domain}
                  </option>
                ))}
              </select>
            </div>
          )}
          {!publicMode && (
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={recommendedOnly}
                onChange={(event) => setRecommendedOnly(event.target.checked)}
              />
              Recommended only
            </label>
          )}
          <input
            type="search"
            placeholder="Search integrations..."
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
      </section>

      <section className="integrations-category-row">
        {categories.map((key) => (
          <button
            key={key}
            className={`btn secondary small ${category === key ? "active" : ""}`}
            onClick={() => setCategory(key)}
          >
            {CATEGORY_LABELS[key] || key}
          </button>
        ))}
      </section>

      {loading && <div className="subtle">Loading integrations...</div>}
      {error && <div className="error-text">{error}</div>}

      <section className="integrations-grid">
        {filtered.map((listing) => (
          <article key={listing.key} className="card integration-card">
            <div className="integration-card-header">
              <div>
                <h3>{listing.name}</h3>
                <div className="subtle">{CATEGORY_LABELS[listing.category] || listing.category}</div>
              </div>
              {listing.is_featured && <span className="badge-tag">Featured</span>}
            </div>
            <p className="subtle">{listing.description}</p>
            <div className="integration-meta">
              {listing.plan_required && (
                <span className="pill">{listing.plan_required.toUpperCase()} plan</span>
              )}
              {listing.recommended && <span className="pill success">Recommended</span>}
            </div>
            <div className="integration-actions">
              {listing.docs_url && (
                <a
                  className="btn secondary small"
                  href={listing.docs_url}
                  onClick={() => logInstallEvent(listing, "clicked")}
                >
                  View guide
                </a>
              )}
              {listing.install_url && (
                <a
                  className="btn primary small"
                  href={listing.install_url}
                  target="_blank"
                  rel="noreferrer"
                  onClick={() => logInstallEvent(listing, listing.install_type === "plugin" || listing.install_type === "app" ? "download" : "clicked")}
                >
                  {listing.install_type === "plugin" || listing.install_type === "app" ? "Install" : "Open"}
                </a>
              )}
              {listing.copy_payload && (
                <CopyButton
                  payload={listing.copy_payload}
                  onCopy={() => logInstallEvent(listing, "copy")}
                />
              )}
            </div>
          </article>
        ))}
      </section>
    </div>
  );
}

export default function IntegrationsDirectoryPage() {
  return <IntegrationsDirectory publicMode={false} />;
}

export function PublicIntegrationsPage() {
  return <IntegrationsDirectory publicMode />;
}
