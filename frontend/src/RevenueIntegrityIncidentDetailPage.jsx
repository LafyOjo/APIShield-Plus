import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch } from "./api";

const STATUS_OPTIONS = [
  { value: "open", label: "Open" },
  { value: "investigating", label: "Investigating" },
  { value: "mitigated", label: "Mitigated" },
  { value: "resolved", label: "Resolved" },
];

const PRIORITY_ORDER = ["P0", "P1", "P2", "P3"];
const ROLE_CAN_MANAGE = new Set(["owner", "admin", "analyst"]);

const formatDateTime = (value) => {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--";
  return date.toLocaleString();
};

const formatPercent = (value) => {
  if (value == null || Number.isNaN(value)) return "--";
  return `${Math.round(value * 1000) / 10}%`;
};

const formatCurrency = (value) => {
  if (value == null || Number.isNaN(value)) return "--";
  return value.toLocaleString(undefined, { style: "currency", currency: "USD" });
};

const formatConfidence = (value) => {
  if (value == null || Number.isNaN(value)) return "--";
  return `${Math.round(value * 100)}%`;
};

const formatDeltaLabel = (value, formatter) => {
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return "--";
  if (numeric === 0) return "flat";
  const direction = numeric > 0 ? "down" : "up";
  const amount = formatter ? formatter(Math.abs(numeric)) : Math.abs(numeric);
  return `${direction} ${amount}`;
};

const toDate = (value) => {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
};

const buildLink = (basePath, params) => {
  if (!params || typeof params !== "object") return basePath;
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value != null && value !== "") {
      search.set(key, String(value));
    }
  });
  const query = search.toString();
  return query ? `${basePath}?${query}` : basePath;
};

const extractEvidenceList = (evidence, key) => {
  if (!evidence || typeof evidence !== "object") return [];
  const bucket = evidence[key];
  if (!bucket || typeof bucket !== "object") return [];
  return Object.entries(bucket)
    .map(([name, count]) => ({ name, count: Number(count) || 0 }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 5);
};

const getIncidentIdFromPath = (path) => {
  const parts = path.split("/").filter(Boolean);
  return parts[parts.length - 1];
};

export default function RevenueIntegrityIncidentDetailPage({ incidentId }) {
  const resolvedIncidentId =
    incidentId || getIncidentIdFromPath(window.location.pathname);
  const [incident, setIncident] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [impactEnabled, setImpactEnabled] = useState(true);
  const [prescriptionsEnabled, setPrescriptionsEnabled] = useState(true);
  const [activeRole, setActiveRole] = useState("");
  const [statusValue, setStatusValue] = useState("open");
  const [notes, setNotes] = useState("");
  const [saveStatus, setSaveStatus] = useState("");
  const [saving, setSaving] = useState(false);
  const [itemStates, setItemStates] = useState({});
  const [memberMap, setMemberMap] = useState({});

  const navigateTo = useCallback((path) => {
    if (!path) return;
    window.history.pushState({}, "", path);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, []);

  const canManagePrescriptions = useMemo(
    () => ROLE_CAN_MANAGE.has(activeRole),
    [activeRole]
  );

  const resolveMemberLabel = useCallback(
    (userId) => {
      if (!userId) return "Unknown";
      const member = memberMap[userId];
      if (!member) return `User #${userId}`;
      return member.display_name || member.email || `User #${userId}`;
    },
    [memberMap]
  );

  useEffect(() => {
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
        const features = entitlements.features || {};
        const enabled = Boolean(features.prescriptions);
        setImpactEnabled(enabled);
        setPrescriptionsEnabled(enabled);
        setActiveRole(String(data?.active_role || "").toLowerCase());
      } catch (err) {
        if (!mounted) return;
        setImpactEnabled(true);
        setPrescriptionsEnabled(true);
        setActiveRole("");
      }
    }
    loadEntitlements();
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (!prescriptionsEnabled || !resolvedIncidentId) return;
    let mounted = true;
    async function loadMembers() {
      try {
        const resp = await apiFetch("/api/v1/members", { skipReauth: true });
        if (!resp.ok) {
          throw new Error("Unable to load members");
        }
        const data = await resp.json();
        if (!mounted) return;
        const nextMap = {};
        (Array.isArray(data) ? data : []).forEach((entry) => {
          const user = entry?.user || {};
          if (!user.id) return;
          nextMap[user.id] = {
            display_name: user.display_name || "",
            email: user.email || "",
          };
        });
        setMemberMap(nextMap);
      } catch (err) {
        if (!mounted) return;
        setMemberMap({});
      }
    }
    loadMembers();
    return () => {
      mounted = false;
    };
  }, [prescriptionsEnabled, resolvedIncidentId]);

  useEffect(() => {
    if (!resolvedIncidentId) return;
    let mounted = true;
    async function loadIncident() {
      setLoading(true);
      setError("");
      try {
        const resp = await apiFetch(`/api/v1/incidents/${resolvedIncidentId}`);
        if (!resp.ok) {
          throw new Error("Unable to load incident");
        }
        const data = await resp.json();
        if (!mounted) return;
        setIncident(data);
        setStatusValue(data.status || "open");
        setNotes(data.notes || "");
      } catch (err) {
        if (!mounted) return;
        setIncident(null);
        setError(err.message || "Unable to load incident");
      } finally {
        if (mounted) setLoading(false);
      }
    }
    loadIncident();
    return () => {
      mounted = false;
    };
  }, [resolvedIncidentId]);

  useEffect(() => {
    if (!incident?.prescription_bundle?.items) return;
    const nextState = {};
    incident.prescription_bundle.items.forEach((item) => {
      nextState[item.id] = {
        status: item.status || "suggested",
        notes: item.notes || "",
        snoozed_until: item.snoozed_until
          - new Date(item.snoozed_until).toISOString().slice(0, 16)
          : "",
        saving: false,
        message: "",
      };
    });
    setItemStates(nextState);
  }, [incident]);

  const handleSave = async () => {
    if (!incident) return;
    setSaving(true);
    setSaveStatus("");
    try {
      const payload = {
        status: statusValue,
        notes,
      };
      const resp = await apiFetch(`/api/v1/incidents/${incident.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!resp.ok) {
        throw new Error("Unable to update incident");
      }
      const updated = await resp.json();
      setIncident(updated);
      setStatusValue(updated.status || "open");
      setNotes(updated.notes || "");
      setSaveStatus("Saved.");
    } catch (err) {
      setSaveStatus(err.message || "Unable to update incident");
    } finally {
      setSaving(false);
    }
  };

  const mapLink = useMemo(
    () => buildLink("/dashboard/security/map", incident?.map_link_params),
    [incident]
  );
  const eventsLink = useMemo(
    () => buildLink("/dashboard/security/events", incident?.map_link_params),
    [incident]
  );

  const evidence = incident?.evidence_summary || incident?.evidence_json || {};
  const topPaths = extractEvidenceList(evidence, "request_paths");
  const topEvents = extractEvidenceList(evidence, "event_types");
  const signalCounts = extractEvidenceList(evidence, "signal_types");
  const impact = incident?.impact_estimate || null;
  const recovery = incident?.recovery_measurement || null;
  const prescriptions = incident?.prescription_bundle?.items || [];

  const groupedPrescriptions = useMemo(() => {
    const groups = {};
    prescriptions.forEach((item) => {
      const priority = String(item.priority || "P2").toUpperCase();
      const key = PRIORITY_ORDER.includes(priority) ? priority : "Other";
      if (!groups[key]) groups[key] = [];
      groups[key].push(item);
    });
    return groups;
  }, [prescriptions]);

  const orderedPriorityGroups = useMemo(() => {
    const items = [];
    PRIORITY_ORDER.forEach((priority) => {
      if (groupedPrescriptions[priority]) {
        items.push({ key: priority, items: groupedPrescriptions[priority] });
      }
    });
    if (groupedPrescriptions.Other) {
      items.push({ key: "Other", items: groupedPrescriptions.Other });
    }
    return items;
  }, [groupedPrescriptions]);

  const appliedHistory = useMemo(() => {
    return prescriptions
      .filter((item) => item.applied_at || item.status === "applied")
      .map((item) => ({
        id: item.id,
        title: item.title,
        applied_at: item.applied_at,
        applied_by: item.applied_by_user_id,
        status: item.status,
      }))
      .sort((a, b) => {
        const aDate = toDate(a.applied_at);
        const bDate = toDate(b.applied_at);
        if (!aDate && !bDate) return 0;
        if (!aDate) return 1;
        if (!bDate) return -1;
        return bDate - aDate;
      });
  }, [prescriptions]);

  const timelineItems = useMemo(() => {
    const items = [];
    if (incident?.first_seen_at) {
      items.push({
        time: incident.first_seen_at,
        title: "Incident detected",
        detail: `Category ${incident.category || "--"} - Severity ${incident.severity || "--"}`,
      });
    }
    if (incident?.last_seen_at) {
      items.push({
        time: incident.last_seen_at,
        title: "Last observed activity",
        detail: "Incident window closed",
      });
    }
    if (evidence?.counts && typeof evidence.counts === "object") {
      const counts = Object.entries(evidence.counts)
        .map(([key, value]) => `${key}: ${value}`)
        .join(", ");
      if (counts) {
        items.push({
          time: incident?.last_seen_at || incident?.first_seen_at,
          title: "Signal spike",
          detail: counts,
        });
      }
    }
    prescriptions.forEach((item) => {
      if (item.applied_at) {
        items.push({
          time: item.applied_at,
          title: `Applied: ${item.title}`,
          detail: `By ${resolveMemberLabel(item.applied_by_user_id)}`,
        });
      }
    });
    if (recovery?.measured_at) {
      items.push({
        time: recovery.measured_at,
        title: "Recovery measured",
        detail: `Recovery ratio ${formatPercent(recovery.recovery_ratio)}`,
      });
    }
    return items
      .filter((entry) => toDate(entry.time))
      .sort((a, b) => new Date(a.time) - new Date(b.time));
  }, [incident, evidence, prescriptions, recovery, resolveMemberLabel]);

  const updateItemState = (itemId, updates) => {
    setItemStates((prev) => ({
      ...prev,
      [itemId]: { ...prev[itemId], ...updates },
    }));
  };

  const handleItemSave = async (item, overrides = {}) => {
    const current = itemStates[item.id] || {};
    const nextStatus = overrides.status -- current.status -- item.status -- "suggested";
    const nextNotes = overrides.notes -- current.notes -- "";
    const nextSnooze = overrides.snoozed_until -- current.snoozed_until -- "";
    updateItemState(item.id, {
      status: nextStatus,
      notes: nextNotes,
      snoozed_until: nextSnooze,
      saving: true,
      message: "",
    });
    try {
      const payload = {
        status: nextStatus,
        notes: nextNotes,
      };
      if (nextStatus === "snoozed" && nextSnooze) {
        payload.snoozed_until = new Date(nextSnooze).toISOString();
      }
      const resp = await apiFetch(`/api/v1/prescriptions/items/${item.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!resp.ok) {
        throw new Error("Unable to update prescription");
      }
      const updated = await resp.json();
      setIncident((prev) => {
        if (!prev?.prescription_bundle?.items) return prev;
        const nextItems = prev.prescription_bundle.items.map((row) =>
          row.id === item.id ? { ...row, ...updated } : row
        );
        return {
          ...prev,
          prescription_bundle: {
            ...prev.prescription_bundle,
            items: nextItems,
          },
        };
      });
      updateItemState(item.id, {
        status: updated.status || nextStatus,
        notes: updated.notes || "",
        snoozed_until: updated.snoozed_until
          - new Date(updated.snoozed_until).toISOString().slice(0, 16)
          : "",
        saving: false,
        message: "Updated.",
      });
    } catch (err) {
      updateItemState(item.id, { saving: false, message: err.message || "Update failed." });
    }
  };

  const handleQuickApply = (item) => {
    if (!canManagePrescriptions) return;
    handleItemSave(item, { status: "applied", snoozed_until: "" });
  };

  if (!resolvedIncidentId) {
    return (
      <div className="card">
        <h2 className="section-title">Incident not found</h2>
        <p className="subtle">Select an incident from the list to see details.</p>
      </div>
    );
  }

  return (
    <div className="stack">
      <section className="card incident-detail-header">
        <div>
          <div className="incident-breadcrumb">
            <button
              className="btn secondary small"
              onClick={() => navigateTo("/dashboard/revenue-integrity/incidents")}
            >
              Back to incidents
            </button>
          </div>
          <h2 className="section-title">Incident #{resolvedIncidentId}</h2>
          <div className="incident-meta">
            <span className={`status-chip ${incident?.status || "open"}`}>
              {incident?.status || "open"}
            </span>
            <span className="subtle">
              Last seen {formatDateTime(incident?.last_seen_at)}
            </span>
          </div>
        </div>
        <div className="incident-actions">
          <button
            className="btn secondary"
            onClick={() => navigateTo(mapLink)}
            disabled={!incident?.map_link_params}
          >
            View on Map
          </button>
          <button
            className="btn secondary"
            onClick={() => navigateTo(eventsLink)}
            disabled={!incident?.map_link_params}
          >
            View Events
          </button>
          <button className="btn secondary" disabled title="Report export coming soon.">
            Export incident report
          </button>
        </div>
      </section>

      {loading && <p className="subtle">Loading incident details...</p>}
      {error && <p className="error-text">{error}</p>}

      {!loading && !error && incident && (
        <>
          <section className="card incident-summary">
            <div className="incident-summary-grid">
              <div>
                <label className="label">Status</label>
                <select
                  className="select"
                  value={statusValue}
                  onChange={(e) => setStatusValue(e.target.value)}
                >
                  {STATUS_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="label">Notes</label>
                <textarea
                  className="textarea"
                  rows={3}
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Add incident notes or mitigation steps..."
                />
              </div>
              <div className="incident-summary-actions">
                <button className="btn primary" onClick={handleSave} disabled={saving}>
                  {saving ? "Saving..." : "Save updates"}
                </button>
                {saveStatus && <div className="subtle">{saveStatus}</div>}
              </div>
            </div>
          </section>

          <section className="incident-grid">
            <div className="card">
              <div className="panel-header">
                <h3 className="section-title">
                  Impact{" "}
                  {!impactEnabled && (
                    <span className="badge pro" title="Upgrade to unlock impact estimates.">
                      Pro
                    </span>
                  )}
                </h3>
                <p className="subtle">Baseline vs observed conversion impact.</p>
              </div>
              {!impactEnabled && (
                <div className="locked-panel">
                  Upgrade to unlock impact estimates and revenue loss analysis.
                </div>
              )}
              {impactEnabled && impact && (
                <div className="impact-metrics">
                  <div className="impact-row">
                    <span>Observed conversion</span>
                    <strong>{formatPercent(impact.observed_rate)}</strong>
                  </div>
                  <div className="impact-row">
                    <span>Baseline conversion</span>
                    <strong>{formatPercent(impact.baseline_rate)}</strong>
                  </div>
                  <div className="impact-row">
                    <span>Delta</span>
                    <strong>{formatPercent(impact.delta_rate)}</strong>
                  </div>
                  <div className="impact-row">
                    <span>Est. lost conversions</span>
                    <strong>{impact.estimated_lost_conversions?.toFixed(1) || "--"}</strong>
                  </div>
                  <div className="impact-row">
                    <span>Est. revenue loss</span>
                    <strong>{formatCurrency(impact.estimated_lost_revenue)}</strong>
                  </div>
                  <div className="impact-row">
                    <span>Confidence</span>
                    <strong>{formatConfidence(impact.confidence)}</strong>
                  </div>
                  <div className="subtle">
                    Window: {formatDateTime(impact.window_start)} to {formatDateTime(impact.window_end)}
                  </div>
                </div>
              )}
              {impactEnabled && !impact && (
                <div className="subtle">No impact estimate generated yet.</div>
              )}
            </div>

            <div className="card">
              <div className="panel-header">
                <h3 className="section-title">Recovery</h3>
                <p className="subtle">Post-fix measurement and recovery score.</p>
              </div>
              {recovery - (
                <div className="recovery-panel">
                  <div className="recovery-gauge">
                    <div className="recovery-gauge-track">
                      <div
                        className="recovery-gauge-fill"
                        style={{
                          width: `${Math.min(
                            100,
                            Math.max(0, Math.round((recovery.recovery_ratio || 0) * 100))
                          )}%`,
                        }}
                      />
                    </div>
                    <div className="recovery-gauge-label">
                      Recovery score {formatPercent(recovery.recovery_ratio)}
                    </div>
                  </div>
                  <div className="recovery-grid">
                    <div className="recovery-metric">
                      <span className="subtle">Baseline</span>
                      <strong>{formatPercent(impact?.baseline_rate)}</strong>
                    </div>
                    <div className="recovery-metric">
                      <span className="subtle">Incident</span>
                      <strong>{formatPercent(impact?.observed_rate)}</strong>
                    </div>
                    <div className="recovery-metric">
                      <span className="subtle">Post-fix</span>
                      <strong>{formatPercent(recovery.post_conversion_rate)}</strong>
                    </div>
                  </div>
                  <div className="recovery-deltas">
                    <div className="recovery-delta">
                      <span className="subtle">Errors</span>
                      <strong>{formatDeltaLabel(recovery.change_in_errors, formatPercent)}</strong>
                    </div>
                    <div className="recovery-delta">
                      <span className="subtle">Threats</span>
                      <strong>
                        {formatDeltaLabel(
                          recovery.change_in_threats,
                          (value) => `${Math.round(value)}`
                        )}
                      </strong>
                    </div>
                    <div className="recovery-delta">
                      <span className="subtle">Confidence</span>
                      <strong>{formatConfidence(recovery.confidence)}</strong>
                    </div>
                  </div>
                  <div className="subtle">
                    Measured {formatDateTime(recovery.measured_at)} - Window{" "}
                    {formatDateTime(recovery.window_start)} to{" "}
                    {formatDateTime(recovery.window_end)}
                  </div>
                </div>
              ) : (
                <div className="subtle">No recovery measurement yet, check back soon.</div>
              )}
            </div>

            <div className="card">
              <div className="panel-header">
                <h3 className="section-title">Evidence</h3>
                <p className="subtle">Signals, paths, and counts tied to the incident.</p>
              </div>
              <div className="evidence-block">
                <div className="evidence-section">
                  <strong>Top paths</strong>
                  {topPaths.length - (
                    <ul>
                      {topPaths.map((item) => (
                        <li key={item.name}>
                          {item.name} <span className="subtle">({item.count})</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <div className="subtle">No paths recorded.</div>
                  )}
                </div>
                <div className="evidence-section">
                  <strong>Event types</strong>
                  {topEvents.length - (
                    <ul>
                      {topEvents.map((item) => (
                        <li key={item.name}>
                          {item.name.replace(/_/g, " ")}{" "}
                          <span className="subtle">({item.count})</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <div className="subtle">No event types recorded.</div>
                  )}
                </div>
                <div className="evidence-section">
                  <strong>Signal types</strong>
                  {signalCounts.length - (
                    <ul>
                      {signalCounts.map((item) => (
                        <li key={item.name}>
                          {item.name.replace(/_/g, " ")}{" "}
                          <span className="subtle">({item.count})</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <div className="subtle">No anomaly signals recorded.</div>
                  )}
                </div>
              </div>
            </div>

            <div className="card">
              <div className="panel-header">
                <h3 className="section-title">
                  Prescriptions{" "}
                  {!prescriptionsEnabled && (
                    <span className="badge pro" title="Upgrade to unlock prescriptions.">
                      Pro
                    </span>
                  )}
                </h3>
                <p className="subtle">Recommended next actions to stop the bleeding.</p>
              </div>
              {!prescriptionsEnabled && (
                <div className="locked-panel">
                  Upgrade to see tailored prescriptions and mitigation steps.
                </div>
              )}
              {prescriptionsEnabled && prescriptions.length > 0 && (
                <div className="prescription-checklist">
                  {!canManagePrescriptions && (
                    <div className="subtle">
                      Read-only: upgrade your role to apply or update prescriptions.
                    </div>
                  )}
                  {orderedPriorityGroups.map((group) => (
                    <div key={group.key} className="prescription-group">
                      <div className="prescription-group-header">
                        <div className="row">
                          <span
                            className={`priority-chip ${
                              group.key === "Other" ? "P3" : group.key
                            }`}
                          >
                            {group.key}
                          </span>
                          <strong>
                            {group.key === "Other" ? "Other priority" : `${group.key} priority`}
                          </strong>
                        </div>
                        <span className="subtle">{group.items.length} items</span>
                      </div>
                      <div className="prescription-list">
                        {group.items.map((item) => {
                          const state = itemStates[item.id] || {};
                          const evidencePaths = item.evidence_json?.paths || [];
                          const statusValue = state.status || item.status || "suggested";
                          const canApply = statusValue === "suggested" || statusValue === "snoozed";
                          return (
                            <div key={item.id} className="prescription-item">
                              <div className="prescription-header">
                                <strong>{item.title}</strong>
                                <div className="prescription-tags">
                                  <span className={`priority-chip ${item.priority || "P2"}`}>
                                    {item.priority || "P2"}
                                  </span>
                                  <span className="effort-chip">{item.effort}</span>
                                  <span className={`status-chip ${statusValue}`}>
                                    {statusValue}
                                  </span>
                                </div>
                              </div>
                              {item.why_it_matters && (
                                <div className="subtle">{item.why_it_matters}</div>
                              )}
                              {(item.steps || []).length > 0 && (
                                <ul className="prescription-steps">
                                  {(item.steps || []).map((step, index) => (
                                    <li key={`${item.id}-step-${index}`}>{step}</li>
                                  ))}
                                </ul>
                              )}
                              {evidencePaths.length > 0 && (
                                <div className="prescription-evidence">
                                  <span className="subtle">Evidence paths:</span>{" "}
                                  {evidencePaths.slice(0, 3).join(", ")}
                                </div>
                              )}
                              {item.applied_at && (
                                <div className="prescription-history">
                                  Applied by {resolveMemberLabel(item.applied_by_user_id)} on{" "}
                                  {formatDateTime(item.applied_at)}
                                </div>
                              )}
                              <div className="prescription-controls">
                                <div className="field">
                                  <label className="label">Status</label>
                                  <select
                                    className="select"
                                    value={statusValue}
                                    onChange={(e) =>
                                      updateItemState(item.id, { status: e.target.value })
                                    }
                                    disabled={!canManagePrescriptions}
                                  >
                                    <option value="suggested">Suggested</option>
                                    <option value="applied">Applied</option>
                                    <option value="dismissed">Dismissed</option>
                                    <option value="snoozed">Snoozed</option>
                                  </select>
                                </div>
                                {statusValue === "snoozed" && (
                                  <div className="field">
                                    <label className="label">Snooze until</label>
                                    <input
                                      className="input"
                                      type="datetime-local"
                                      value={state.snoozed_until || ""}
                                      onChange={(e) =>
                                        updateItemState(item.id, { snoozed_until: e.target.value })
                                      }
                                      disabled={!canManagePrescriptions}
                                    />
                                  </div>
                                )}
                                <div className="field">
                                  <label className="label">Notes</label>
                                  <textarea
                                    className="textarea"
                                    rows={2}
                                    value={state.notes || ""}
                                    onChange={(e) =>
                                      updateItemState(item.id, { notes: e.target.value })
                                    }
                                    placeholder="Add notes or evidence..."
                                    disabled={!canManagePrescriptions}
                                  />
                                </div>
                                <div className="prescription-actions">
                                  {canApply && (
                                    <button
                                      className="btn primary small"
                                      onClick={() => handleQuickApply(item)}
                                      disabled={!canManagePrescriptions || state.saving}
                                      title={
                                        canManagePrescriptions
                                          - "Apply prescription"
                                          : "Insufficient role to apply"
                                      }
                                    >
                                      Apply
                                    </button>
                                  )}
                                  <button
                                    className="btn secondary small"
                                    onClick={() => handleItemSave(item)}
                                    disabled={!canManagePrescriptions || state.saving}
                                  >
                                    {state.saving ? "Updating..." : "Update"}
                                  </button>
                                  {state.message && (
                                    <span className="subtle">{state.message}</span>
                                  )}
                                </div>
                              </div>
                              <div className="prescription-footer">
                                <span className="subtle">
                                  Expected: {item.expected_effect}
                                </span>
                                {item.automation_possible && (
                                  <span className="badge pro">Automation possible</span>
                                )}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                  <div className="prescription-history-block">
                    <strong>Applied history</strong>
                    {appliedHistory.length === 0 && (
                      <div className="subtle">No applied prescriptions yet.</div>
                    )}
                    {appliedHistory.length > 0 && (
                      <ul className="prescription-history-list">
                        {appliedHistory.map((entry) => (
                          <li key={entry.id}>
                            {entry.title} -{" "}
                            {entry.applied_at
                              ? formatDateTime(entry.applied_at)
                              : "No apply time"}{" "}
                            - {resolveMemberLabel(entry.applied_by)}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              )}
              {prescriptionsEnabled && prescriptions.length === 0 && (
                <div className="subtle">No prescriptions generated yet.</div>
              )}
            </div>
          </section>

          <section className="card incident-timeline">
            <div className="panel-header">
              <h3 className="section-title">Timeline</h3>
              <p className="subtle">Incident progression, actions, and recovery checks.</p>
            </div>
            {timelineItems.length === 0 && (
              <div className="subtle">No timeline events yet.</div>
            )}
            {timelineItems.length > 0 && (
              <div className="timeline-list">
                {timelineItems.map((entry, index) => (
                  <div key={`${entry.title}-${index}`} className="timeline-item">
                    <div className="timeline-time">{formatDateTime(entry.time)}</div>
                    <div className="timeline-content">
                      <span className="timeline-dot" />
                      <div className="timeline-title">{entry.title}</div>
                      {entry.detail && <div className="subtle">{entry.detail}</div>}
                    </div>
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
