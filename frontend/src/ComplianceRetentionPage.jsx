import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch } from "./api";

const DATASETS = [
  {
    key: "behaviour_events",
    label: "Behaviour events",
    description: "Browser activity, page views, and telemetry.",
  },
  {
    key: "security_events",
    label: "Security events",
    description: "Threat detections, rule triggers, and anomalies.",
  },
  {
    key: "incidents",
    label: "Incidents",
    description: "Aggregated incident records and investigations.",
  },
  {
    key: "audit_logs",
    label: "Audit logs",
    description: "Compliance audit trail for admin actions.",
  },
  {
    key: "geo_agg",
    label: "Geo aggregates",
    description: "Hourly geo activity buckets for map views.",
  },
];

const buildDatasetIndex = (policies = []) => {
  const map = {};
  for (const policy of policies) {
    map[policy.dataset_key] = policy;
  }
  return map;
};

const navigate = (path) => {
  if (window.location.pathname === path) return;
  window.history.pushState({}, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
};

export default function ComplianceRetentionPage() {
  const [policies, setPolicies] = useState([]);
  const [drafts, setDrafts] = useState({});
  const [loading, setLoading] = useState(false);
  const [statusByKey, setStatusByKey] = useState({});
  const [error, setError] = useState("");

  const datasetIndex = useMemo(() => buildDatasetIndex(policies), [policies]);

  const hydrateDrafts = useCallback((items) => {
    const next = {};
    for (const policy of items) {
      next[policy.dataset_key] = {
        retention_days: policy.retention_days ?? "",
        is_legal_hold_enabled: Boolean(policy.is_legal_hold_enabled),
        legal_hold_reason: policy.legal_hold_reason || "",
      };
    }
    setDrafts(next);
  }, []);

  const loadPolicies = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const resp = await apiFetch("/api/v1/retention/policies");
      if (!resp.ok) {
        throw new Error(await resp.text());
      }
      const data = await resp.json();
      setPolicies(data || []);
      hydrateDrafts(data || []);
    } catch (err) {
      setError(err.message || "Unable to load retention policies.");
    } finally {
      setLoading(false);
    }
  }, [hydrateDrafts]);

  useEffect(() => {
    loadPolicies();
  }, [loadPolicies]);

  const updateDraft = (datasetKey, patch) => {
    setDrafts((prev) => ({
      ...prev,
      [datasetKey]: { ...prev[datasetKey], ...patch },
    }));
  };

  const handleSave = async (datasetKey) => {
    const draft = drafts[datasetKey];
    if (!draft) return;
    const retentionDays = Number.parseInt(draft.retention_days, 10);
    if (!retentionDays || retentionDays <= 0) {
      setStatusByKey((prev) => ({
        ...prev,
        [datasetKey]: "Retention days must be a positive number.",
      }));
      return;
    }
    if (draft.is_legal_hold_enabled && !draft.legal_hold_reason.trim()) {
      setStatusByKey((prev) => ({
        ...prev,
        [datasetKey]: "Legal hold reason is required.",
      }));
      return;
    }
    setStatusByKey((prev) => ({ ...prev, [datasetKey]: "Saving..." }));
    try {
      const resp = await apiFetch("/api/v1/retention/policies", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          dataset_key: datasetKey,
          retention_days: retentionDays,
          is_legal_hold_enabled: draft.is_legal_hold_enabled,
          legal_hold_reason: draft.legal_hold_reason.trim(),
        }),
      });
      if (!resp.ok) {
        throw new Error(await resp.text());
      }
      const updated = await resp.json();
      setPolicies((prev) =>
        prev.map((item) => (item.dataset_key === datasetKey ? updated : item))
      );
      updateDraft(datasetKey, {
        retention_days: updated.retention_days,
        is_legal_hold_enabled: updated.is_legal_hold_enabled,
        legal_hold_reason: updated.legal_hold_reason || "",
      });
      setStatusByKey((prev) => ({ ...prev, [datasetKey]: "Saved." }));
    } catch (err) {
      setStatusByKey((prev) => ({
        ...prev,
        [datasetKey]: err.message || "Save failed.",
      }));
    }
  };

  return (
    <div className="app-container stack">
      <header className="header bar">
        <h1 className="dashboard-header">Compliance & Retention</h1>
        <div className="row">
          <button
            className="btn secondary nav-tab"
            onClick={() => navigate("/dashboard/compliance/audit")}
          >
            Audit export
          </button>
          <button className="btn secondary nav-tab active">Retention policies</button>
        </div>
      </header>

      <section className="card">
        <h2 className="section-title">Retention policies & legal hold</h2>
        <p className="subtle">
          Customize retention windows per dataset. Legal hold pauses deletion while an
          investigation or compliance review is active.
        </p>
        <div className="row" style={{ marginBottom: "1rem" }}>
          <button className="btn secondary" onClick={loadPolicies} disabled={loading}>
            {loading ? "Refreshing..." : "Refresh policies"}
          </button>
          {error && <span className="help" style={{ color: "var(--danger)" }}>{error}</span>}
        </div>
        <table className="table">
          <thead>
            <tr>
              <th>Dataset</th>
              <th>Retention days</th>
              <th>Legal hold</th>
              <th>Reason</th>
              <th>Status</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {DATASETS.map((dataset) => {
              const policy = datasetIndex[dataset.key] || {};
              const draft = drafts[dataset.key] || {
                retention_days: policy.retention_days || "",
                is_legal_hold_enabled: Boolean(policy.is_legal_hold_enabled),
                legal_hold_reason: policy.legal_hold_reason || "",
              };
              return (
                <tr key={dataset.key}>
                  <td>
                    <div style={{ fontWeight: 600 }}>{dataset.label}</div>
                    <div className="subtle" style={{ fontSize: "0.85rem" }}>
                      {dataset.description}
                    </div>
                  </td>
                  <td>
                    <input
                      className="input"
                      type="number"
                      min="1"
                      value={draft.retention_days}
                      onChange={(e) =>
                        updateDraft(dataset.key, { retention_days: e.target.value })
                      }
                    />
                  </td>
                  <td>
                    <label className="row" style={{ gap: "0.5rem" }}>
                      <input
                        type="checkbox"
                        checked={draft.is_legal_hold_enabled}
                        onChange={(e) =>
                          updateDraft(dataset.key, {
                            is_legal_hold_enabled: e.target.checked,
                          })
                        }
                      />
                      {draft.is_legal_hold_enabled ? "Enabled" : "Off"}
                    </label>
                  </td>
                  <td>
                    <input
                      className="input"
                      type="text"
                      placeholder="Reason required when enabled"
                      value={draft.legal_hold_reason}
                      onChange={(e) =>
                        updateDraft(dataset.key, { legal_hold_reason: e.target.value })
                      }
                    />
                  </td>
                  <td className="subtle">{statusByKey[dataset.key] || ""}</td>
                  <td>
                    <button
                      className="btn primary"
                      onClick={() => handleSave(dataset.key)}
                    >
                      Save
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
    </div>
  );
}
