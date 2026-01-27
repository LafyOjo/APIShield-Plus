import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch, ACTIVE_TENANT_KEY } from "./api";
import { useDemoData } from "./useDemoData";
import TourOverlay from "./TourOverlay";
import { useTour } from "./useTour";

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
  const activeTenant = localStorage.getItem(ACTIVE_TENANT_KEY) || "";
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
  const [activeTab, setActiveTab] = useState("prescriptions");
  const [copyStatus, setCopyStatus] = useState("");
  const [verificationRuns, setVerificationRuns] = useState([]);
  const [verificationMessage, setVerificationMessage] = useState("");
  const [verifying, setVerifying] = useState(false);
  const incidentTour = useTour("incidents", activeTenant);
  const { enabled: includeDemo } = useDemoData();

  const incidentTourSteps = useMemo(
    () => [
      {
        selector: '[data-tour="incident-impact"]',
        title: "Impact overview",
        body: "See conversion loss and confidence for this incident window.",
      },
      {
        selector: '[data-tour="incident-prescriptions"]',
        title: "Prescriptions & playbooks",
        body: "Review suggested fixes or stack-specific playbooks to resolve fast.",
      },
      {
        selector: '[data-tour="incident-map-link"]',
        title: "Trace origin on the map",
        body: "Jump into the geo map with filters pre-applied for this incident.",
      },
    ],
    []
  );

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
        const params = includeDemo ? "?include_demo=true" : "";
        const resp = await apiFetch(`/api/v1/incidents/${resolvedIncidentId}${params}`);
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
  }, [resolvedIncidentId, includeDemo]);

  useEffect(() => {
    if (!resolvedIncidentId) return;
    let mounted = true;
    async function loadVerificationRuns() {
      try {
        const params = includeDemo ? "?include_demo=true" : "";
        const resp = await apiFetch(
          `/api/v1/incidents/${resolvedIncidentId}/verification${params}`,
          { skipReauth: true }
        );
        if (!resp.ok) {
          throw new Error("Unable to load verification runs");
        }
        const data = await resp.json();
        if (!mounted) return;
        setVerificationRuns(Array.isArray(data) ? data : []);
      } catch (err) {
        if (!mounted) return;
        setVerificationRuns([]);
      }
    }
    loadVerificationRuns();
    return () => {
      mounted = false;
    };
  }, [resolvedIncidentId, includeDemo]);

  useEffect(() => {
    if (!incident) return;
    const hasPrescriptions =
      Array.isArray(incident?.prescription_bundle?.items) &&
      incident.prescription_bundle.items.length > 0;
    const hasPlaybook =
      Array.isArray(incident?.remediation_playbook?.sections) &&
      incident.remediation_playbook.sections.length > 0;
    const hasPresets =
      Array.isArray(incident?.protection_presets) && incident.protection_presets.length > 0;
    if (!hasPrescriptions && hasPlaybook) {
      setActiveTab("playbook");
    } else if (!hasPrescriptions && !hasPlaybook && hasPresets) {
      setActiveTab("presets");
    }
  }, [incident]);

  useEffect(() => {
    if (!incident?.prescription_bundle?.items) return;
    const nextState = {};
    incident.prescription_bundle.items.forEach((item) => {
      nextState[item.id] = {
        status: item.status || "suggested",
        notes: item.notes || "",
        snoozed_until: item.snoozed_until
          ? new Date(item.snoozed_until).toISOString().slice(0, 16)
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
      const params = includeDemo ? "?include_demo=true" : "";
      const resp = await apiFetch(`/api/v1/incidents/${incident.id}${params}`, {
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

  const mapLink = useMemo(() => {
    if (!incident?.map_link_params) return "/dashboard/security/map";
    const params = { ...incident.map_link_params };
    if (includeDemo) params.demo = "1";
    return buildLink("/dashboard/security/map", params);
  }, [incident, includeDemo]);
  const eventsLink = useMemo(() => {
    if (!incident?.map_link_params) return "/dashboard/security/events";
    const params = { ...incident.map_link_params };
    if (includeDemo) params.demo = "1";
    return buildLink("/dashboard/security/events", params);
  }, [incident, includeDemo]);

  const evidence = incident?.evidence_summary || incident?.evidence_json || {};
  const topPaths = extractEvidenceList(evidence, "request_paths");
  const topEvents = extractEvidenceList(evidence, "event_types");
  const signalCounts = extractEvidenceList(evidence, "signal_types");
  const impact = incident?.impact_estimate || null;
  const recovery = incident?.recovery_measurement || null;
  const prescriptions = incident?.prescription_bundle?.items || [];
  const presets = incident?.protection_presets || [];
  const playbook = incident?.remediation_playbook || null;
  const playbookSections = Array.isArray(playbook?.sections)
    ? playbook.sections
    : Array.isArray(playbook?.sections_json)
      ? playbook.sections_json
      : [];

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
    const nextStatus = overrides.status ?? current.status ?? item.status ?? "suggested";
    const nextNotes = overrides.notes ?? current.notes ?? "";
    const nextSnooze = overrides.snoozed_until ?? current.snoozed_until ?? "";
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
          ? new Date(updated.snoozed_until).toISOString().slice(0, 16)
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

  const handleCopy = async (value) => {
    if (!value) return;
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(value);
        setCopyStatus("Copied to clipboard.");
      } else {
        window.prompt("Copy this preset:", value);
        setCopyStatus("Ready to copy.");
      }
    } catch (err) {
      setCopyStatus("Unable to copy preset.");
    } finally {
      setTimeout(() => setCopyStatus(""), 2500);
    }
  };

  const handleRunVerification = async () => {
    if (!incident) return;
    setVerifying(true);
    setVerificationMessage("");
    try {
      const params = includeDemo ? "?include_demo=true" : "";
      const resp = await apiFetch(`/api/v1/incidents/${incident.id}/verification${params}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      if (!resp.ok) {
        throw new Error("Verification run failed");
      }
      const data = await resp.json();
      setVerificationRuns((prev) => [data, ...(Array.isArray(prev) ? prev : [])]);
      setVerificationMessage("Verification run completed.");
    } catch (err) {
      setVerificationMessage(err.message || "Unable to run verification.");
    } finally {
      setVerifying(false);
      setTimeout(() => setVerificationMessage(""), 2500);
    }
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
            data-tour="incident-map-link"
            onClick={() => navigateTo(mapLink)}
            disabled={!incident?.map_link_params}
          >
            View on Map
          </button>
          <button
            className="btn secondary"
            onClick={() =>
              navigateTo(
                includeDemo
                  ? `/dashboard/remediation/${resolvedIncidentId}?demo=1`
                  : `/dashboard/remediation/${resolvedIncidentId}`
              )
            }
          >
            Remediation workspace
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
          <button className="btn secondary" onClick={incidentTour.restart}>
            Start tour
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
            <div className="card" data-tour="incident-impact">
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
              {recovery ? (
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
                  {topPaths.length ? (
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
                  {topEvents.length ? (
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
                  {signalCounts.length ? (
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

            <div className="card" data-tour="incident-prescriptions">
              <div className="panel-header incident-tab-header">
                <div>
                  <h3 className="section-title">
                    {activeTab === "playbook" ? "Playbook" : "Prescriptions"}{" "}
                    {activeTab === "prescriptions" && !prescriptionsEnabled && (
                      <span className="badge pro" title="Upgrade to unlock prescriptions.">
                        Pro
                      </span>
                    )}
                  </h3>
                  <p className="subtle">
                    {activeTab === "playbook"
                      ? "Stack-aware remediation steps and verification guidance."
                      : "Recommended next actions to stop the bleeding."}
                  </p>
                </div>
                <div className="incident-tab-bar">
                  <button
                    type="button"
                    className={`btn secondary nav-tab ${
                      activeTab === "prescriptions" ? "active" : ""
                    }`}
                    onClick={() => setActiveTab("prescriptions")}
                  >
                    Prescriptions
                  </button>
                  <button
                    type="button"
                    className={`btn secondary nav-tab ${
                      activeTab === "playbook" ? "active" : ""
                    }`}
                    onClick={() => setActiveTab("playbook")}
                  >
                    Playbook
                  </button>
                  <button
                    type="button"
                    className={`btn secondary nav-tab ${
                      activeTab === "presets" ? "active" : ""
                    }`}
                    onClick={() => setActiveTab("presets")}
                  >
                    Presets
                  </button>
                </div>
              </div>

              {activeTab === "prescriptions" && (
                <>
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
                                            updateItemState(item.id, {
                                              snoozed_until: e.target.value,
                                            })
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
                                              ? "Apply prescription"
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
                </>
              )}

              {activeTab === "playbook" && (
                <div className="playbook-panel">
                  {!playbook && (
                    <div className="subtle">No playbook generated for this incident yet.</div>
                  )}
                  {playbook && (
                    <>
                      <div className="playbook-meta">
                        <span className="badge">{playbook.stack_type || "custom"}</span>
                        <span className="subtle">Version {playbook.version}</span>
                        <span className="subtle status-chip">{playbook.status}</span>
                      </div>
                      {playbookSections.length === 0 && (
                        <div className="subtle">Playbook sections are unavailable.</div>
                      )}
                      {playbookSections.map((section, index) => (
                        <div key={`${section.title}-${index}`} className="playbook-section">
                          <div className="playbook-section-header">
                            <strong>{section.title || "Untitled section"}</strong>
                            {section.risk_level && (
                              <span className={`risk-chip ${section.risk_level}`}>
                                {section.risk_level}
                              </span>
                            )}
                          </div>
                          {section.context && <p className="subtle">{section.context}</p>}
                          {(section.steps || []).length > 0 && (
                            <ol className="playbook-steps">
                              {(section.steps || []).map((step, stepIndex) => (
                                <li key={`${section.title}-step-${stepIndex}`}>{step}</li>
                              ))}
                            </ol>
                          )}
                          {(section.code_snippets || []).length > 0 && (
                            <div className="playbook-snippets">
                              {(section.code_snippets || []).map((snippet, snippetIndex) => (
                                <div
                                  key={`${section.title}-snippet-${snippetIndex}`}
                                  className="playbook-snippet"
                                >
                                  {snippet.language && (
                                    <div className="snippet-language">{snippet.language}</div>
                                  )}
                                  <pre>{snippet.snippet}</pre>
                                </div>
                              ))}
                            </div>
                          )}
                          {(section.verification_steps || []).length > 0 && (
                            <div className="playbook-checks">
                              <strong>Verification</strong>
                              <ul>
                                {(section.verification_steps || []).map((step, verifyIndex) => (
                                  <li key={`${section.title}-verify-${verifyIndex}`}>{step}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                          {(section.rollback_steps || []).length > 0 && (
                            <div className="playbook-checks">
                              <strong>Rollback</strong>
                              <ul>
                                {(section.rollback_steps || []).map((step, rollbackIndex) => (
                                  <li key={`${section.title}-rollback-${rollbackIndex}`}>{step}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                      ))}
                    </>
                  )}
                </div>
              )}

              {activeTab === "presets" && (
                <div className="preset-panel">
                  {copyStatus && <div className="subtle">{copyStatus}</div>}
                  {presets.length === 0 && (
                    <div className="subtle">No protection presets generated yet.</div>
                  )}
                  {presets.map((preset) => {
                    const content = preset.content_json || {};
                    const formats = content.formats || {};
                    const copyBlocks = formats.copy_blocks || [];
                    const jsonExport = formats.json;
                    const markdownExport = formats.markdown;
                    return (
                      <div key={preset.id} className="preset-card">
                        <div className="preset-header">
                          <div>
                            <strong>{content.title || preset.preset_type}</strong>
                            <p className="subtle">{content.summary || "Preset guidance."}</p>
                          </div>
                          <span className="badge">{preset.preset_type}</span>
                        </div>
                        {copyBlocks.length > 0 && (
                          <div className="preset-blocks">
                            {copyBlocks.map((block, index) => (
                              <div key={`${preset.id}-block-${index}`} className="preset-block">
                                <div className="preset-block-header">
                                  <span className="subtle">{block.label || "Copy block"}</span>
                                  <button
                                    className="btn secondary small"
                                    onClick={() => handleCopy(block.content)}
                                  >
                                    Copy
                                  </button>
                                </div>
                                <pre>{block.content}</pre>
                              </div>
                            ))}
                          </div>
                        )}
                        {jsonExport && (
                          <div className="preset-block">
                            <div className="preset-block-header">
                              <span className="subtle">JSON export</span>
                              <button
                                className="btn secondary small"
                                onClick={() =>
                                  handleCopy(JSON.stringify(jsonExport, null, 2))
                                }
                              >
                                Copy JSON
                              </button>
                            </div>
                            <pre>{JSON.stringify(jsonExport, null, 2)}</pre>
                          </div>
                        )}
                        {markdownExport && (
                          <div className="preset-block">
                            <div className="preset-block-header">
                              <span className="subtle">Markdown</span>
                              <button
                                className="btn secondary small"
                                onClick={() => handleCopy(markdownExport)}
                              >
                                Copy Markdown
                              </button>
                            </div>
                            <pre>{markdownExport}</pre>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
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

          <section className="card verification-panel">
              <div className="panel-header verification-header">
                <div>
                  <h3 className="section-title">Verification</h3>
                  <p className="subtle">
                    Run checks to confirm protections reduced threats and recovered conversions.
                  </p>
                </div>
                <div className="row">
                  <button
                    className="btn primary"
                    onClick={handleRunVerification}
                    disabled={verifying || !canManagePrescriptions}
                    title={
                      canManagePrescriptions ? "Run verification checks" : "Insufficient role"
                    }
                  >
                    {verifying ? "Running..." : "Run verification"}
                  </button>
                </div>
              </div>
              {!canManagePrescriptions && (
                <div className="subtle">
                  Read-only: upgrade your role to run verification checks.
                </div>
              )}
            {verificationMessage && <div className="subtle">{verificationMessage}</div>}
            {verificationRuns.length === 0 && (
              <div className="subtle">No verification runs yet.</div>
            )}
            {verificationRuns.length > 0 && (
              <div className="verification-run">
                <div className="verification-summary">
                  <span className={`status-chip ${verificationRuns[0].status}`}>
                    {verificationRuns[0].status}
                  </span>
                  <span className="subtle">
                    Last run {formatDateTime(verificationRuns[0].created_at)}
                  </span>
                </div>
                <div className="verification-checks">
                  {(verificationRuns[0].checks || []).map((check, index) => (
                    <div key={`${check.check_type}-${index}`} className="verification-check">
                      <div className="verification-check-header">
                        <strong>{check.label || check.check_type}</strong>
                        <span className={`status-chip ${check.status}`}>{check.status}</span>
                      </div>
                      <div className="verification-metrics">
                        <span className="subtle">
                          Before: {check.before ?? "--"}
                        </span>
                        <span className="subtle">
                          After: {check.after ?? "--"}
                        </span>
                        <span className="subtle">
                          Delta:{" "}
                          {check.delta != null
                            ? `${Math.round(check.delta * 100)}%`
                            : "--"}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </section>
        </>
      )}
      <TourOverlay
        steps={incidentTourSteps}
        isOpen={incidentTour.open}
        onComplete={incidentTour.complete}
        onDismiss={incidentTour.dismiss}
      />
    </div>
  );
}
