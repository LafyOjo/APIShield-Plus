import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch, API_BASE } from "./api";

const TYPE_LABELS = {
  playbook: "Playbook",
  preset: "Preset",
  alert_rules: "Alert rules",
};

const formatJson = (value) => {
  try {
    return JSON.stringify(value, null, 2);
  } catch (err) {
    return String(value || "");
  }
};

export function MarketplaceTemplateDetail({ templateId, publicMode = false }) {
  const resolvedId =
    templateId || window.location.pathname.split("/").filter(Boolean).slice(-1)[0];
  const [template, setTemplate] = useState(null);
  const [incidentId, setIncidentId] = useState("");
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const loadTemplate = useCallback(async () => {
    if (!resolvedId) return;
    setLoading(true);
    setError("");
    try {
      const endpoint = publicMode
        ? `${API_BASE}/public/marketplace/${resolvedId}`
        : `/api/v1/marketplace/templates/${resolvedId}`;
      const resp = publicMode ? await fetch(endpoint) : await apiFetch(endpoint);
      if (!resp.ok) throw new Error("Unable to load template");
      const data = await resp.json();
      setTemplate(data);
    } catch (err) {
      setError(err.message || "Unable to load template");
    } finally {
      setLoading(false);
    }
  }, [resolvedId, publicMode]);

  useEffect(() => {
    loadTemplate();
  }, [loadTemplate]);

  const requiresIncident = useMemo(() => {
    return template?.template_type === "playbook" || template?.template_type === "preset";
  }, [template]);

  const handleImport = async () => {
    if (!template) return;
    if (requiresIncident && !incidentId) {
      setError("Incident ID is required for this template.");
      return;
    }
    setStatus("");
    setError("");
    try {
      const resp = await apiFetch(`/api/v1/marketplace/templates/${template.id}/import`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          incident_id: requiresIncident ? Number(incidentId) : null,
        }),
      });
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      setStatus(`Imported successfully (event #${data.import_event_id}).`);
    } catch (err) {
      setError(err.message || "Import failed.");
    }
  };

  const navigateBack = () => {
    const target = publicMode ? "/marketplace" : "/dashboard/marketplace";
    window.history.pushState({}, "", target);
    window.dispatchEvent(new PopStateEvent("popstate"));
  };

  if (!resolvedId) {
    return (
      <div className="card">
        <h2 className="section-title">Template not found</h2>
        <p className="subtle">Select a template to view details.</p>
      </div>
    );
  }

  return (
    <div className="stack marketplace-detail">
      <section className="card marketplace-detail-header">
        <div>
          <h2 className="section-title">Template detail</h2>
          <p className="subtle">Preview and import a trusted remediation template.</p>
        </div>
        <button className="btn secondary" onClick={navigateBack}>
          Back to marketplace
        </button>
      </section>

      {loading && <div className="subtle">Loading template...</div>}
      {error && <div className="error-text">{error}</div>}
      {status && <div className="subtle">{status}</div>}

      {template && (
        <>
          <section className="card marketplace-detail-card">
            <div className="marketplace-card-header">
              <div>
                <h3>{template.title}</h3>
                <div className="subtle">{TYPE_LABELS[template.template_type] || template.template_type}</div>
              </div>
              <span className="badge-tag">{template.template_type}</span>
            </div>
            <p className="subtle">{template.description}</p>
            {template.safety_notes && (
              <div className="marketplace-safety">
                <strong>Safety notes</strong>
                <p className="subtle">{template.safety_notes}</p>
              </div>
            )}
            <div className="marketplace-meta">
              {template.stack_type && <span className="pill">{template.stack_type}</span>}
              {(template.tags || []).map((tag) => (
                <span key={`${template.id}-${tag}`} className="pill">
                  {tag}
                </span>
              ))}
            </div>
          </section>

          {!publicMode && (
            <section className="card marketplace-import">
              <div className="panel-header">
                <h3 className="section-title">Import</h3>
                <button className="btn primary" onClick={handleImport}>
                  Import template
                </button>
              </div>
              {requiresIncident && (
                <div className="field">
                  <label className="label">Incident ID</label>
                  <input
                    className="input"
                    type="number"
                    value={incidentId}
                    onChange={(event) => setIncidentId(event.target.value)}
                    placeholder="e.g. 1204"
                  />
                  <div className="subtle small">
                    Required to attach playbooks and presets to a specific incident.
                  </div>
                </div>
              )}
            </section>
          )}

          <section className="card marketplace-preview">
            <h3 className="section-title">Preview</h3>
            {template.template_type === "playbook" && (
              <div className="playbook-panel">
                {(template.content_json?.sections || []).map((section, index) => (
                  <div key={`${template.id}-section-${index}`} className="playbook-section">
                    <div className="playbook-section-header">
                      <strong>{section.title}</strong>
                      {section.risk_level && <span className={`risk-chip ${section.risk_level}`}>{section.risk_level}</span>}
                    </div>
                    {section.context && <p className="subtle">{section.context}</p>}
                    <ul className="playbook-steps">
                      {(section.steps || []).map((step, stepIndex) => (
                        <li key={`${template.id}-step-${stepIndex}`}>{step}</li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            )}

            {template.template_type === "preset" && (
              <div className="preset-panel">
                <div className="preset-card">
                  <div className="preset-header">
                    <div>
                      <strong>{template.content_json?.title || template.title}</strong>
                      <p className="subtle">{template.content_json?.summary || template.description}</p>
                    </div>
                  </div>
                  <div className="preset-blocks">
                    {(template.content_json?.formats?.copy_blocks || []).map((block, index) => (
                      <div key={`${template.id}-block-${index}`} className="preset-block">
                        <div className="preset-block-header">
                          <span className="subtle">{block.label}</span>
                        </div>
                        <pre>{block.content}</pre>
                      </div>
                    ))}
                    {(!template.content_json?.formats?.copy_blocks || template.content_json?.formats?.copy_blocks?.length === 0) && (
                      <div className="preset-block">
                        <div className="preset-block-header">
                          <span className="subtle">JSON</span>
                        </div>
                        <pre>{formatJson(template.content_json)}</pre>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}

            {template.template_type === "alert_rules" && (
              <div className="marketplace-rules">
                {(template.content_json?.rules || []).map((rule, index) => (
                  <div key={`${template.id}-rule-${index}`} className="marketplace-rule-card">
                    <strong>{rule.name || "Alert rule"}</strong>
                    <div className="subtle">Trigger: {rule.trigger_type}</div>
                    {rule.filters && (
                      <pre>{formatJson(rule.filters)}</pre>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}

export default function MarketplaceTemplateDetailPage({ templateId }) {
  return <MarketplaceTemplateDetail templateId={templateId} publicMode={false} />;
}

export function PublicMarketplaceTemplateDetailPage({ templateId }) {
  return <MarketplaceTemplateDetail templateId={templateId} publicMode />;
}
