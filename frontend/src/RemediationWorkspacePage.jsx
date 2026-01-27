import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch, ACTIVE_TENANT_KEY } from "./api";
import TourOverlay from "./TourOverlay";
import { useTour } from "./useTour";
import { useDemoData } from "./useDemoData";

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

export default function RemediationWorkspacePage({ incidentId }) {
  const resolvedIncidentId =
    incidentId || window.location.pathname.split("/").filter(Boolean).slice(-1)[0];
  const activeTenant = localStorage.getItem(ACTIVE_TENANT_KEY) || "";
  const [incident, setIncident] = useState(null);
  const [verificationRuns, setVerificationRuns] = useState([]);
  const [trustSummary, setTrustSummary] = useState(null);
  const [leakSummary, setLeakSummary] = useState(null);
  const [activeRole, setActiveRole] = useState("");
  const [playbookChecks, setPlaybookChecks] = useState({});
  const [presetApplied, setPresetApplied] = useState({});
  const [copyStatus, setCopyStatus] = useState("");
  const [verifying, setVerifying] = useState(false);
  const [verificationMessage, setVerificationMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const remediationTour = useTour("remediation", activeTenant);
  const { enabled: includeDemo } = useDemoData();

  const remediationTourSteps = useMemo(
    () => [
      {
        selector: '[data-tour="remediation-playbook"]',
        title: "Follow the playbook",
        body: "Work through stack-specific steps to remediate the incident.",
      },
      {
        selector: '[data-tour="remediation-presets"]',
        title: "Apply protection presets",
        body: "Copy CSP or rate limit configs tailored for this incident.",
      },
      {
        selector: '[data-tour="remediation-verify"]',
        title: "Verify recovery",
        body: "Run checks to confirm threat volume and conversion recover.",
      },
      {
        selector: '[data-tour="remediation-report"]',
        title: "Export the report",
        body: "Download evidence and verification results for stakeholders.",
      },
    ],
    []
  );

  const canManage = useMemo(() => ROLE_CAN_MANAGE.has(activeRole), [activeRole]);

  useEffect(() => {
    let mounted = true;
    async function loadRole() {
      try {
        const resp = await apiFetch("/api/v1/me", { skipReauth: true });
        if (!resp.ok) {
          throw new Error("Unable to load role");
        }
        const data = await resp.json();
        if (!mounted) return;
        setActiveRole(String(data?.active_role || "").toLowerCase());
      } catch (err) {
        if (!mounted) return;
        setActiveRole("");
      }
    }
    loadRole();
    return () => {
      mounted = false;
    };
  }, []);

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
      } catch (err) {
        if (!mounted) return;
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
    if (!incident) return;
    const sections = incident?.remediation_playbook?.sections || [];
    const nextChecks = {};
    sections.forEach((section, sectionIndex) => {
      (section.steps || []).forEach((_, stepIndex) => {
        const key = `${sectionIndex}-${stepIndex}`;
        nextChecks[key] = playbookChecks[key] || false;
      });
    });
    setPlaybookChecks(nextChecks);
  }, [incident, includeDemo]);

  useEffect(() => {
    if (!resolvedIncidentId) return;
    let mounted = true;
    async function loadVerificationRuns() {
      try {
        const params = includeDemo ? "?include_demo=true" : "";
        const resp = await apiFetch(`/api/v1/incidents/${resolvedIncidentId}/verification${params}`, {
          skipReauth: true,
        });
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
    if (!incident?.first_seen_at || !incident?.last_seen_at) return;
    let mounted = true;
    async function loadTrustAndLeak() {
      try {
        const params = new URLSearchParams();
        params.set("from", incident.first_seen_at);
        params.set("to", incident.last_seen_at);
        if (incident.website_id != null) params.set("website_id", incident.website_id);
        if (incident.environment_id != null) params.set("env_id", incident.environment_id);
        if (includeDemo) params.set("include_demo", "true");
        const trustResp = await apiFetch(`/api/v1/trust/snapshots?${params.toString()}`);
        if (trustResp.ok) {
          const trustData = await trustResp.json();
          if (mounted && Array.isArray(trustData) && trustData.length > 0) {
            const avg =
              trustData.reduce((sum, item) => sum + Number(item.trust_score || 0), 0) /
              trustData.length;
            setTrustSummary({
              average: avg,
              latest: trustData[trustData.length - 1]?.trust_score ?? null,
            });
          }
        }
        const leakResp = await apiFetch(`/api/v1/revenue/leaks?${params.toString()}`);
        if (leakResp.ok) {
          const leakData = await leakResp.json();
          const items = leakData?.items || [];
          const match =
            items.find((item) => (item.incident_ids || []).includes(incident.id)) || items[0];
          if (mounted) {
            setLeakSummary(match || null);
          }
        }
      } catch (err) {
        if (!mounted) return;
        setTrustSummary(null);
        setLeakSummary(null);
      }
    }
    loadTrustAndLeak();
    return () => {
      mounted = false;
    };
  }, [incident]);

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

  const handleApplyPrescription = async (item) => {
    if (!canManage) return;
    try {
      const resp = await apiFetch(`/api/v1/prescriptions/items/${item.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: "applied" }),
      });
      if (!resp.ok) {
        throw new Error("Unable to apply prescription");
      }
      const updated = await resp.json();
      setIncident((prev) => {
        if (!prev?.prescription_bundle?.items) return prev;
        const nextItems = prev.prescription_bundle.items.map((row) =>
          row.id === item.id ? { ...row, ...updated } : row
        );
        return {
          ...prev,
          prescription_bundle: { ...prev.prescription_bundle, items: nextItems },
        };
      });
    } catch (err) {
      // no-op for now
    }
  };

  const downloadReport = async (format) => {
    if (!incident) return;
    try {
      const params = new URLSearchParams();
      params.set("format", format);
      if (includeDemo) params.set("include_demo", "true");
      const resp = await apiFetch(`/api/v1/incidents/${incident.id}/report?${params.toString()}`);
      if (!resp.ok) {
        throw new Error("Unable to export report");
      }
      const blob = await resp.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `incident-${incident.id}-report.${format === "csv" ? "csv" : "json"}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setError(err.message || "Unable to export report");
    }
  };

  const prescriptions = incident?.prescription_bundle?.items || [];
  const playbookSections = incident?.remediation_playbook?.sections || [];
  const presets = incident?.protection_presets || [];
  const mapLink = useMemo(() => {
    if (!incident?.map_link_params) return "/dashboard/security/map";
    const params = { ...incident.map_link_params };
    if (includeDemo) params.demo = "1";
    return buildLink("/dashboard/security/map", params);
  }, [incident, includeDemo]);

  const appliedPrescriptions = prescriptions.filter((item) => item.status === "applied").length;
  const totalPlaybookSteps = playbookSections.reduce(
    (sum, section) => sum + (section.steps || []).length,
    0
  );
  const checkedPlaybookSteps = Object.values(playbookChecks).filter(Boolean).length;
  const appliedPresetsCount = Object.values(presetApplied).filter(Boolean).length;
  const totalProgressItems =
    totalPlaybookSteps + prescriptions.length + presets.length || 0;
  const completedItems = checkedPlaybookSteps + appliedPrescriptions + appliedPresetsCount;
  const progressPercent =
    totalProgressItems > 0 ? Math.round((completedItems / totalProgressItems) * 100) : 0;

  if (!resolvedIncidentId) {
    return (
      <div className="card">
        <h2 className="section-title">Remediation workspace not found</h2>
        <p className="subtle">Select an incident to begin remediation.</p>
      </div>
    );
  }

  return (
    <div className="stack">
      <section className="card remediation-header">
        <div>
          <h2 className="section-title">Remediation Workspace</h2>
          <p className="subtle">Incident #{resolvedIncidentId} guided workflow.</p>
        </div>
        <div className="remediation-progress">
          <span className="subtle">Progress</span>
          <strong>{progressPercent}%</strong>
          <div className="progress-track">
            <div className="progress-fill" style={{ width: `${progressPercent}%` }} />
          </div>
        </div>
        <div className="row">
          <button className="btn secondary" onClick={remediationTour.restart}>
            Start tour
          </button>
        </div>
      </section>

      {loading && <p className="subtle">Loading remediation workspace...</p>}
      {error && <p className="error-text">{error}</p>}

      {!loading && incident && (
        <>
          <section className="card remediation-summary">
            <div className="panel-header">
              <h3 className="section-title">Incident Summary</h3>
              <span className={`status-chip ${incident.status}`}>{incident.status}</span>
            </div>
            <div className="remediation-summary-grid">
              <div>
                <div className="subtle">Impact</div>
                <strong>{formatCurrency(incident?.impact_estimate?.estimated_lost_revenue)}</strong>
                <div className="subtle">
                  Delta {formatPercent(incident?.impact_estimate?.delta_rate)}
                </div>
              </div>
              <div>
                <div className="subtle">Trust score</div>
                <strong>{trustSummary?.latest ?? "--"}</strong>
                <div className="subtle">
                  Avg {trustSummary?.average ? Math.round(trustSummary.average) : "--"}
                </div>
              </div>
              <div>
                <div className="subtle">Leak estimate</div>
                <strong>{formatCurrency(leakSummary?.total_lost_revenue)}</strong>
                <div className="subtle">
                  Trust delta {leakSummary?.trust_score_delta ?? "--"}
                </div>
              </div>
              <div>
                <div className="subtle">Window</div>
                <strong>{formatDateTime(incident.first_seen_at)}</strong>
                <div className="subtle">{formatDateTime(incident.last_seen_at)}</div>
              </div>
            </div>
          </section>

          <section className="card remediation-map">
            <div className="panel-header">
              <h3 className="section-title">Origin Map</h3>
              <button
                className="btn secondary"
                onClick={() => {
                  window.history.pushState({}, "", mapLink);
                  window.dispatchEvent(new PopStateEvent("popstate"));
                }}
              >
                Open map
              </button>
            </div>
            <p className="subtle">
              Map filters are locked to the incident window. Use the map to inspect source regions.
            </p>
          </section>

          <section className="card remediation-playbook" data-tour="remediation-playbook">
            <div className="panel-header">
              <h3 className="section-title">Playbook</h3>
              <span className="badge">{incident?.remediation_playbook?.stack_type || "custom"}</span>
            </div>
            {playbookSections.length === 0 && (
              <div className="subtle">No playbook generated yet.</div>
            )}
            {playbookSections.map((section, sectionIndex) => (
              <div key={`${section.title}-${sectionIndex}`} className="remediation-section">
                <strong>{section.title}</strong>
                {section.context && <p className="subtle">{section.context}</p>}
                <ul className="remediation-checklist">
                  {(section.steps || []).map((step, stepIndex) => {
                    const key = `${sectionIndex}-${stepIndex}`;
                    return (
                      <li key={key}>
                        <label className="row">
                          <input
                            type="checkbox"
                            checked={Boolean(playbookChecks[key])}
                            onChange={() =>
                              setPlaybookChecks((prev) => ({
                                ...prev,
                                [key]: !prev[key],
                              }))
                            }
                          />
                          <span>{step}</span>
                        </label>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </section>

          <section className="card remediation-presets" data-tour="remediation-presets">
            <div className="panel-header">
              <h3 className="section-title">Protection Presets</h3>
            </div>
            {copyStatus && <div className="subtle">{copyStatus}</div>}
            {presets.length === 0 && <div className="subtle">No presets generated.</div>}
            {presets.map((preset) => {
              const formats = preset.content_json?.formats || {};
              const blocks = formats.copy_blocks || [];
              return (
                <div key={preset.id} className="preset-card">
                  <div className="preset-header">
                    <div>
                      <strong>{preset.content_json?.title || preset.preset_type}</strong>
                      <p className="subtle">{preset.content_json?.summary}</p>
                    </div>
                    <label className="row">
                      <input
                        type="checkbox"
                        checked={Boolean(presetApplied[preset.id])}
                        onChange={() =>
                          setPresetApplied((prev) => ({
                            ...prev,
                            [preset.id]: !prev[preset.id],
                          }))
                        }
                      />
                      <span className="subtle">Applied</span>
                    </label>
                  </div>
                  {blocks.map((block, index) => (
                    <div key={`${preset.id}-block-${index}`} className="preset-block">
                      <div className="preset-block-header">
                        <span className="subtle">{block.label}</span>
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
              );
            })}
          </section>

          <section className="card remediation-actions">
            <div className="panel-header">
              <h3 className="section-title">Apply Actions</h3>
              {!canManage && (
                <span className="subtle">Read-only for your role.</span>
              )}
            </div>
            {prescriptions.length === 0 && (
              <div className="subtle">No prescriptions available.</div>
            )}
            {prescriptions.map((item) => (
              <div key={item.id} className="remediation-action">
                <div>
                  <strong>{item.title}</strong>
                  <div className="subtle">
                    {item.why_it_matters || item.expected_effect || "Recommended action."}
                  </div>
                </div>
                <div className="row">
                  <span className={`status-chip ${item.status}`}>{item.status}</span>
                  <button
                    className="btn secondary small"
                    disabled={!canManage || item.status === "applied"}
                    onClick={() => handleApplyPrescription(item)}
                  >
                    {item.status === "applied" ? "Applied" : "Mark applied"}
                  </button>
                </div>
              </div>
            ))}
          </section>

          <section className="card remediation-verify" data-tour="remediation-verify">
            <div className="panel-header">
              <h3 className="section-title">Verification</h3>
              <button
                className="btn primary"
                onClick={handleRunVerification}
                disabled={!canManage || verifying}
              >
                {verifying ? "Running..." : "Run verification"}
              </button>
            </div>
            {verificationMessage && <div className="subtle">{verificationMessage}</div>}
            {verificationRuns.length === 0 && (
              <div className="subtle">No verification runs yet.</div>
            )}
            {verificationRuns.length > 0 && (
              <div className="verification-checks">
                {(verificationRuns[0].checks || []).map((check, index) => (
                  <div key={`${check.check_type}-${index}`} className="verification-check">
                    <div className="verification-check-header">
                      <strong>{check.label || check.check_type}</strong>
                      <span className={`status-chip ${check.status}`}>{check.status}</span>
                    </div>
                    <div className="verification-metrics">
                      <span className="subtle">Before: {check.before ?? "--"}</span>
                      <span className="subtle">After: {check.after ?? "--"}</span>
                      <span className="subtle">
                        Delta:{" "}
                        {check.delta != null ? `${Math.round(check.delta * 100)}%` : "--"}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="card remediation-report" data-tour="remediation-report">
            <div className="panel-header">
              <h3 className="section-title">Export Report</h3>
              <div className="row">
                <button className="btn secondary" onClick={() => downloadReport("json")}>
                  Download JSON
                </button>
                <button className="btn secondary" onClick={() => downloadReport("csv")}>
                  Download CSV
                </button>
              </div>
            </div>
            <p className="subtle">
              Export includes incident evidence, prescriptions, recovery, and verification results.
            </p>
          </section>
        </>
      )}
      <TourOverlay
        steps={remediationTourSteps}
        isOpen={remediationTour.open}
        onComplete={remediationTour.complete}
        onDismiss={remediationTour.dismiss}
      />
    </div>
  );
}
