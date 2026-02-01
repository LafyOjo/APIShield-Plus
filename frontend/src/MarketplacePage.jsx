import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch, ACTIVE_TENANT_KEY, API_BASE } from "./api";

const TYPE_LABELS = {
  playbook: "Playbook",
  preset: "Preset",
  alert_rules: "Alert rules",
};

const normalize = (value) => String(value || "").toLowerCase();

export function MarketplaceDirectory({ publicMode = false }) {
  const [templates, setTemplates] = useState([]);
  const [templateType, setTemplateType] = useState("all");
  const [stackFilter, setStackFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const activeTenant = localStorage.getItem(ACTIVE_TENANT_KEY) || "";

  const loadTemplates = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const endpoint = publicMode
        ? `${API_BASE}/public/marketplace`
        : "/api/v1/marketplace/templates";
      const resp = publicMode ? await fetch(endpoint) : await apiFetch(endpoint);
      if (!resp.ok) throw new Error("Unable to load templates");
      const data = await resp.json();
      setTemplates(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err.message || "Unable to load templates");
      setTemplates([]);
    } finally {
      setLoading(false);
    }
  }, [publicMode]);

  useEffect(() => {
    loadTemplates();
  }, [loadTemplates, activeTenant]);

  const typeOptions = useMemo(() => {
    const set = new Set(templates.map((item) => item.template_type));
    return ["all", ...Array.from(set).sort()];
  }, [templates]);

  const stackOptions = useMemo(() => {
    const set = new Set(templates.map((item) => item.stack_type).filter(Boolean));
    return ["all", ...Array.from(set).sort()];
  }, [templates]);

  const filtered = useMemo(() => {
    let items = templates;
    if (templateType !== "all") {
      items = items.filter((item) => item.template_type === templateType);
    }
    if (stackFilter !== "all") {
      items = items.filter((item) => (item.stack_type || "custom") === stackFilter);
    }
    const query = normalize(search);
    if (query) {
      items = items.filter((item) => {
        const haystack = [item.title, item.description, item.template_type]
          .filter(Boolean)
          .map(normalize)
          .join(" ");
        return haystack.includes(query);
      });
    }
    return items;
  }, [templates, templateType, stackFilter, search]);

  const openTemplate = (templateId) => {
    const target = publicMode
      ? `/marketplace/${templateId}`
      : `/dashboard/marketplace/${templateId}`;
    window.history.pushState({}, "", target);
    window.dispatchEvent(new PopStateEvent("popstate"));
  };

  return (
    <div className="stack marketplace-page">
      <section className="card marketplace-header">
        <div>
          <h2 className="section-title">Template Marketplace</h2>
          <p className="subtle">
            Import trusted playbooks, presets, and alert rules curated by the APIShield+ team.
          </p>
        </div>
        <div className="marketplace-controls">
          <div className="marketplace-select">
            <label className="label">Type</label>
            <select
              className="select"
              value={templateType}
              onChange={(event) => setTemplateType(event.target.value)}
            >
              {typeOptions.map((key) => (
                <option key={key} value={key}>
                  {TYPE_LABELS[key] || key}
                </option>
              ))}
            </select>
          </div>
          <div className="marketplace-select">
            <label className="label">Stack</label>
            <select
              className="select"
              value={stackFilter}
              onChange={(event) => setStackFilter(event.target.value)}
            >
              {stackOptions.map((key) => (
                <option key={key} value={key}>
                  {key === "all" ? "All stacks" : key}
                </option>
              ))}
            </select>
          </div>
          <input
            type="search"
            placeholder="Search templates..."
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
      </section>

      {loading && <div className="subtle">Loading templates...</div>}
      {error && <div className="error-text">{error}</div>}

      <section className="marketplace-grid">
        {filtered.map((template) => (
          <article key={template.id} className="card marketplace-card">
            <div className="marketplace-card-header">
              <div>
                <h3>{template.title}</h3>
                <div className="subtle">{TYPE_LABELS[template.template_type] || template.template_type}</div>
              </div>
              <span className="badge-tag">{template.template_type}</span>
            </div>
            <p className="subtle">{template.description}</p>
            <div className="marketplace-meta">
              {template.stack_type && <span className="pill">{template.stack_type}</span>}
              {template.tags?.map((tag) => (
                <span key={`${template.id}-${tag}`} className="pill">
                  {tag}
                </span>
              ))}
            </div>
            <div className="marketplace-actions">
              <button className="btn secondary small" onClick={() => openTemplate(template.id)}>
                View details
              </button>
            </div>
          </article>
        ))}
      </section>
    </div>
  );
}

export default function MarketplacePage() {
  return <MarketplaceDirectory publicMode={false} />;
}

export function PublicMarketplacePage() {
  return <MarketplaceDirectory publicMode />;
}
