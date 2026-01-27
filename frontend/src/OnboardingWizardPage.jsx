import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch, ACTIVE_TENANT_KEY } from "./api";
import DemoDataToggle from "./DemoDataToggle";
import { useDemoData } from "./useDemoData";

const STEP_ORDER = [
  "create_website",
  "install_agent",
  "verify_events",
  "enable_geo_map",
  "create_alert",
  "finish",
];

const STEP_LABELS = {
  create_website: "Create website + environment",
  install_agent: "Install the agent snippet",
  verify_events: "Verify events are flowing",
  enable_geo_map: "Enable the Geo Map",
  create_alert: "Create first notification rule",
  finish: "Finish and launch",
};

const STEP_DESCRIPTIONS = {
  create_website:
    "Register your first domain so we can generate environments and keys.",
  install_agent:
    "Paste the snippet into your site to start collecting secure events.",
  verify_events:
    "We will confirm that events arrive in the last 10 minutes.",
  enable_geo_map:
    "Review geo privacy defaults and open the map experience.",
  create_alert:
    "Create at least one notification rule so you get alerted quickly.",
  finish:
    "Review your setup and jump into the dashboard.",
};

const HELP_LINKS = {
  create_website: "/dashboard/help?doc=getting-started",
  install_agent: "/dashboard/help?doc=install-agent",
  verify_events: "/dashboard/help?doc=troubleshooting-events",
  enable_geo_map: "/dashboard/help?doc=security-best-practices",
  create_alert: "/dashboard/help?doc=security-best-practices",
};

const formatDateTime = (value) => {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString();
};

const ensureArray = (value) => (Array.isArray(value) ? value : []);

export default function OnboardingWizardPage() {
  const [tenants, setTenants] = useState([]);
  const [activeTenant, setActiveTenant] = useState(
    localStorage.getItem(ACTIVE_TENANT_KEY) || ""
  );
  const [state, setState] = useState(null);
  const [websites, setWebsites] = useState([]);
  const [selectedWebsiteId, setSelectedWebsiteId] = useState("");
  const [installData, setInstallData] = useState(null);
  const [stackProfile, setStackProfile] = useState(null);
  const [selectedEnvId, setSelectedEnvId] = useState("");
  const [domain, setDomain] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [loading, setLoading] = useState(false);
  const [actionError, setActionError] = useState("");
  const [actionNotice, setActionNotice] = useState("");
  const [creatingWebsite, setCreatingWebsite] = useState(false);
  const [creatingKey, setCreatingKey] = useState(false);
  const [verifyingEvents, setVerifyingEvents] = useState(false);
  const [demoStatus, setDemoStatus] = useState("");
  const [seedingDemo, setSeedingDemo] = useState(false);
  const { enabled: includeDemo, setEnabled: setIncludeDemo } = useDemoData();
  const navigateTo = useCallback((path) => {
    if (!path) return;
    window.history.pushState({}, "", path);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, []);

  const completedSteps = useMemo(
    () => new Set(ensureArray(state?.completed_steps)),
    [state?.completed_steps]
  );
  const progress = Math.round(
    (completedSteps.size / STEP_ORDER.length) * 100
  );

  const refreshState = useCallback(async () => {
    if (!activeTenant) return;
    setLoading(true);
    setActionError("");
    try {
      const resp = await apiFetch("/api/v1/onboarding/state");
      if (!resp.ok) {
        throw new Error("Unable to load onboarding state");
      }
      const data = await resp.json();
      setState(data);
    } catch (err) {
      setActionError(err.message || "Unable to load onboarding state");
    } finally {
      setLoading(false);
    }
  }, [activeTenant]);

  const loadTenants = useCallback(async () => {
    try {
      const resp = await apiFetch("/api/v1/tenants");
      if (!resp.ok) {
        throw new Error("Unable to load tenants");
      }
      const data = await resp.json();
      setTenants(data);
      if (!activeTenant && data.length) {
        setActiveTenant(data[0].slug);
        localStorage.setItem(ACTIVE_TENANT_KEY, String(data[0].slug));
      }
    } catch (err) {
      setActionError(err.message || "Unable to load tenants");
    }
  }, [activeTenant]);

  const loadWebsites = useCallback(async () => {
    if (!activeTenant) return;
    try {
      const resp = await apiFetch("/api/v1/websites");
      if (!resp.ok) {
        throw new Error("Unable to load websites");
      }
      const data = await resp.json();
      setWebsites(data);
    } catch (err) {
      setWebsites([]);
    }
  }, [activeTenant]);

  const loadInstallData = useCallback(
    async (websiteId) => {
      if (!websiteId) return;
      try {
        const resp = await apiFetch(`/api/v1/websites/${websiteId}/install`);
        if (!resp.ok) {
          throw new Error("Unable to load install instructions");
        }
        const data = await resp.json();
        setInstallData(data);
      } catch (err) {
        setInstallData(null);
      }
    },
    []
  );

  const loadStackProfile = useCallback(async (websiteId) => {
    if (!websiteId) return;
    try {
      const resp = await apiFetch(`/api/v1/websites/${websiteId}/stack`);
      if (!resp.ok) {
        throw new Error("Unable to load stack profile");
      }
      const data = await resp.json();
      setStackProfile(data);
    } catch (err) {
      setStackProfile(null);
    }
  }, []);

  useEffect(() => {
    loadTenants();
  }, [loadTenants]);

  useEffect(() => {
    if (!activeTenant) {
      localStorage.removeItem(ACTIVE_TENANT_KEY);
      setState(null);
      setWebsites([]);
      setInstallData(null);
      setSelectedWebsiteId("");
      return;
    }
    localStorage.setItem(ACTIVE_TENANT_KEY, activeTenant);
    refreshState();
    loadWebsites();
  }, [activeTenant, refreshState, loadWebsites]);

  useEffect(() => {
    if (state?.first_website_id) {
      setSelectedWebsiteId(String(state.first_website_id));
      return;
    }
    if (!selectedWebsiteId && websites.length) {
      setSelectedWebsiteId(String(websites[0].id));
    }
  }, [state?.first_website_id, websites, selectedWebsiteId]);

  useEffect(() => {
    if (selectedWebsiteId) {
      loadInstallData(selectedWebsiteId);
      loadStackProfile(selectedWebsiteId);
    } else {
      setInstallData(null);
      setStackProfile(null);
    }
  }, [selectedWebsiteId, loadInstallData, loadStackProfile]);

  useEffect(() => {
    const envs = installData?.environments || [];
    if (!envs.length) {
      setSelectedEnvId("");
      return;
    }
    if (!selectedEnvId || !envs.some((env) => String(env.id) === String(selectedEnvId))) {
      setSelectedEnvId(String(envs[0].id));
    }
  }, [installData, selectedEnvId]);

  useEffect(() => {
    if (!state) return;
    if (completedSteps.has("verify_events")) return;
    if (!selectedWebsiteId) return;
    const interval = setInterval(() => {
      refreshState();
    }, 15000);
    return () => clearInterval(interval);
  }, [completedSteps, refreshState, selectedWebsiteId, state]);

  const completeStep = useCallback(
    async (step, extra = {}) => {
      setActionError("");
      setActionNotice("");
      const resp = await apiFetch("/api/v1/onboarding/complete-step", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ step, ...extra }),
      });
      if (!resp.ok) {
        let detail = "Unable to complete step";
        try {
          const data = await resp.json();
          if (data?.detail) detail = data.detail;
        } catch (err) {
          // ignore
        }
        setActionError(detail);
        return null;
      }
      const data = await resp.json();
      setState(data);
      setActionNotice("Step marked complete.");
      return data;
    },
    []
  );

  const handleCreateWebsite = async () => {
    if (!domain) {
      setActionError("Domain is required.");
      return;
    }
    setCreatingWebsite(true);
    setActionError("");
    try {
      const resp = await apiFetch("/api/v1/websites", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          domain,
          display_name: displayName || undefined,
        }),
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data?.detail || "Unable to create website");
      }
      const data = await resp.json();
      setDomain("");
      setDisplayName("");
      setSelectedWebsiteId(String(data.id));
      await completeStep("create_website", { website_id: data.id });
      loadWebsites();
    } catch (err) {
      setActionError(err.message || "Unable to create website");
    } finally {
      setCreatingWebsite(false);
    }
  };

  const handleCreateKey = async () => {
    if (!selectedEnvId) return;
    setCreatingKey(true);
    setActionError("");
    try {
      const resp = await apiFetch(`/api/v1/environments/${selectedEnvId}/keys`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: "Production Key" }),
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data?.detail || "Unable to create key");
      }
      await resp.json();
      await loadInstallData(selectedWebsiteId);
    } catch (err) {
      setActionError(err.message || "Unable to create key");
    } finally {
      setCreatingKey(false);
    }
  };

  const handleVerifyEvents = async () => {
    if (!selectedWebsiteId) {
      setActionError("Select a website first.");
      return;
    }
    setVerifyingEvents(true);
    const response = await completeStep("verify_events", {
      website_id: Number(selectedWebsiteId),
      environment_id: selectedEnvId ? Number(selectedEnvId) : undefined,
    });
    if (response && response.verified_event_received_at) {
      setActionNotice("Events detected. You're live!");
    }
    setVerifyingEvents(false);
  };

  const handleSeedDemo = async () => {
    if (!activeTenant) {
      setDemoStatus("Select a tenant to seed demo data.");
      return;
    }
    setSeedingDemo(true);
    setDemoStatus("");
    try {
      const resp = await apiFetch("/api/v1/demo/seed", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ force: false }),
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data?.detail || "Unable to seed demo data");
      }
      const data = await resp.json();
      setIncludeDemo(true);
      setDemoStatus(
        `Demo data ready. Expires ${formatDateTime(data.expires_at)}.`
      );
    } catch (err) {
      setDemoStatus(err.message || "Unable to seed demo data");
    } finally {
      setSeedingDemo(false);
    }
  };

  const handleTenantChange = (value) => {
    setActiveTenant(value);
    if (!value) {
      localStorage.removeItem(ACTIVE_TENANT_KEY);
    } else {
      localStorage.setItem(ACTIVE_TENANT_KEY, value);
    }
  };

  const activeEnv = useMemo(() => {
    const envs = installData?.environments || [];
    return envs.find((env) => String(env.id) === String(selectedEnvId)) || envs[0];
  }, [installData, selectedEnvId]);

  const activeKey = activeEnv?.keys?.[0] || null;
  const snippet = activeKey?.snippet || "";

  const hasWebsite = Boolean(selectedWebsiteId);
  const hasSnippet = Boolean(snippet);

  return (
    <div className="stack onboarding-page">
      <section className="card onboarding-header">
        <div>
          <h2 className="section-title">Tenant Onboarding Wizard</h2>
          <p className="subtle">
            Follow these steps to connect your first site and unlock dashboards.
          </p>
        </div>
        <div className="onboarding-progress">
          <div className="subtle">Progress</div>
          <div className="progress-track">
            <div
              className="progress-fill"
              style={{ width: `${progress}%` }}
            />
          </div>
          <strong>{progress}% complete</strong>
        </div>
        <div className="onboarding-tenant">
          <label className="label">Active tenant</label>
          <select
            className="select"
            value={activeTenant}
            onChange={(e) => handleTenantChange(e.target.value)}
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

      {loading && <div className="card subtle">Loading onboarding state...</div>}
      {actionError && <div className="card error-text">{actionError}</div>}
      {actionNotice && <div className="card subtle">{actionNotice}</div>}

      <section className="card onboarding-demo">
        <div>
          <h3 className="section-title">Try demo data</h3>
          <p className="subtle">
            Explore incidents, maps, and remediation flows without installing the agent.
          </p>
        </div>
        <div className="row">
          <button
            className="btn primary"
            onClick={handleSeedDemo}
            disabled={seedingDemo}
          >
            {seedingDemo ? "Seeding demo..." : "Generate demo data"}
          </button>
          <DemoDataToggle
            enabled={includeDemo}
            onToggle={() => setIncludeDemo((prev) => !prev)}
          />
        </div>
        {demoStatus && <div className="help">{demoStatus}</div>}
      </section>

      <section className="onboarding-steps">
        <div
          className={`card onboarding-step ${completedSteps.has("create_website") ? "done" : ""}`}
        >
          <div className="onboarding-step-header">
            <div>
              <h3 className="section-title">{STEP_LABELS.create_website}</h3>
              <p className="subtle">{STEP_DESCRIPTIONS.create_website}</p>
            </div>
            <span className="onboarding-status">
              {completedSteps.has("create_website") ? "Completed" : "Required"}
            </span>
          </div>
          <div className="onboarding-form">
            <div className="field">
              <label className="label">Domain</label>
              <input
                type="text"
                placeholder="example.com"
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
              />
            </div>
            <div className="field">
              <label className="label">Display name</label>
              <input
                type="text"
                placeholder="Example Store"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
              />
            </div>
          </div>
          <div className="onboarding-actions">
            <button
              className="btn primary"
              onClick={handleCreateWebsite}
              disabled={creatingWebsite || !activeTenant}
            >
              {creatingWebsite ? "Creating..." : "Create website"}
            </button>
            <button
              className="btn secondary"
              onClick={() => navigateTo(HELP_LINKS.create_website)}
            >
              View guide
            </button>
          </div>
          {hasWebsite && (
            <div className="subtle">
              Selected website:{" "}
              {websites.find((site) => String(site.id) === selectedWebsiteId)?.domain ||
                "Unknown"}
            </div>
          )}
        </div>

        <div
          className={`card onboarding-step ${completedSteps.has("install_agent") ? "done" : ""}`}
        >
          <div className="onboarding-step-header">
            <div>
              <h3 className="section-title">{STEP_LABELS.install_agent}</h3>
              <p className="subtle">{STEP_DESCRIPTIONS.install_agent}</p>
            </div>
            <span className="onboarding-status">
              {completedSteps.has("install_agent") ? "Completed" : "Required"}
            </span>
          </div>
          {!hasWebsite && (
            <div className="locked-panel">
              Create a website first to generate an environment and snippet.
            </div>
          )}
          {hasWebsite && (
            <>
              <div className="onboarding-inline">
                <div className="field">
                  <label className="label">Website</label>
                  <select
                    className="select"
                    value={selectedWebsiteId}
                    onChange={(e) => setSelectedWebsiteId(e.target.value)}
                  >
                    {websites.map((site) => (
                      <option key={site.id} value={site.id}>
                        {site.display_name || site.domain}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label className="label">Environment</label>
                  <select
                    className="select"
                    value={selectedEnvId}
                    onChange={(e) => setSelectedEnvId(e.target.value)}
                    disabled={!installData?.environments?.length}
                  >
                    {installData?.environments?.map((env) => (
                      <option key={env.id} value={env.id}>
                        {env.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="onboarding-snippet">
                {stackProfile?.stack_type === "wordpress" && (
                  <div className="onboarding-plugin-note">
                    <strong>WordPress detected.</strong> You can install the plugin
                    (coming soon) or paste the snippet manually.
                  </div>
                )}
                {hasSnippet ? (
                  <>
                    <label className="label">Embed snippet</label>
                    <pre>{snippet}</pre>
                  </>
                ) : (
                  <div className="locked-panel">
                    No API keys found. Generate one to see the snippet.
                  </div>
                )}
              </div>
              <div className="onboarding-actions">
                {!hasSnippet && (
                  <button
                    className="btn secondary"
                    onClick={handleCreateKey}
                    disabled={creatingKey || !selectedEnvId}
                  >
                    {creatingKey ? "Generating..." : "Generate API key"}
                  </button>
                )}
                <button
                  className="btn secondary"
                  onClick={() => navigateTo(HELP_LINKS.install_agent)}
                >
                  Install guide
                </button>
                <button
                  className="btn primary"
                  onClick={() =>
                    completeStep("install_agent", {
                      website_id: Number(selectedWebsiteId),
                      environment_id: selectedEnvId ? Number(selectedEnvId) : undefined,
                    })
                  }
                  disabled={!hasSnippet}
                >
                  Mark installed
                </button>
              </div>
            </>
          )}
        </div>

        <div
          className={`card onboarding-step ${completedSteps.has("verify_events") ? "done" : ""}`}
        >
          <div className="onboarding-step-header">
            <div>
              <h3 className="section-title">{STEP_LABELS.verify_events}</h3>
              <p className="subtle">{STEP_DESCRIPTIONS.verify_events}</p>
            </div>
            <span className="onboarding-status">
              {completedSteps.has("verify_events") ? "Completed" : "Pending"}
            </span>
          </div>
          {!hasWebsite && (
            <div className="locked-panel">Create a website and install the agent first.</div>
          )}
          {hasWebsite && (
            <>
              <div className="subtle">
                {state?.verified_event_received_at
                  ? `Last event received at ${formatDateTime(
                      state.verified_event_received_at
                    )}`
                  : "No recent events detected yet."}
              </div>
              <div className="onboarding-actions">
                <button
                  className="btn primary"
                  onClick={handleVerifyEvents}
                  disabled={verifyingEvents}
                >
                  {verifyingEvents ? "Checking..." : "Check for events"}
                </button>
                <button
                  className="btn secondary"
                  onClick={() => navigateTo(HELP_LINKS.verify_events)}
                >
                  Troubleshooting
                </button>
              </div>
            </>
          )}
        </div>

        <div
          className={`card onboarding-step ${completedSteps.has("enable_geo_map") ? "done" : ""}`}
        >
          <div className="onboarding-step-header">
            <div>
              <h3 className="section-title">{STEP_LABELS.enable_geo_map}</h3>
              <p className="subtle">{STEP_DESCRIPTIONS.enable_geo_map}</p>
            </div>
            <span className="onboarding-status">
              {completedSteps.has("enable_geo_map") ? "Completed" : "Optional"}
            </span>
          </div>
          <div className="subtle">
            Geo Map uses hashed IPs by default. Raw IPs stay within your retention
            window. Upgrade plans unlock city and ASN detail.
          </div>
          <div className="onboarding-actions">
            <button
              className="btn secondary"
              onClick={() => navigateTo("/dashboard/security/map")}
            >
              Open Geo Map
            </button>
            <button
              className="btn secondary"
              onClick={() => navigateTo(HELP_LINKS.enable_geo_map)}
            >
              Geo privacy guide
            </button>
            <button
              className="btn primary"
              onClick={() => completeStep("enable_geo_map")}
            >
              Mark enabled
            </button>
          </div>
        </div>

        <div
          className={`card onboarding-step ${completedSteps.has("create_alert") ? "done" : ""}`}
        >
          <div className="onboarding-step-header">
            <div>
              <h3 className="section-title">{STEP_LABELS.create_alert}</h3>
              <p className="subtle">{STEP_DESCRIPTIONS.create_alert}</p>
            </div>
            <span className="onboarding-status">
              {completedSteps.has("create_alert") ? "Completed" : "Pending"}
            </span>
          </div>
          <div className="subtle">
            Create a Slack, email, or webhook rule so the team is alerted fast.
          </div>
          <div className="onboarding-actions">
            <button
              className="btn secondary"
              onClick={() => navigateTo("/dashboard/settings/notifications")}
            >
              Open notifications
            </button>
            <button
              className="btn secondary"
              onClick={() => navigateTo(HELP_LINKS.create_alert)}
            >
              Alert guide
            </button>
            <button
              className="btn primary"
              onClick={() => completeStep("create_alert")}
            >
              Mark rule created
            </button>
          </div>
        </div>

        <div
          className={`card onboarding-step ${completedSteps.has("finish") ? "done" : ""}`}
        >
          <div className="onboarding-step-header">
            <div>
              <h3 className="section-title">{STEP_LABELS.finish}</h3>
              <p className="subtle">{STEP_DESCRIPTIONS.finish}</p>
            </div>
            <span className="onboarding-status">
              {completedSteps.has("finish") ? "Completed" : "Final step"}
            </span>
          </div>
          <div className="onboarding-actions">
            <button
              className="btn secondary"
              onClick={() => navigateTo("/dashboard/security/map")}
            >
              View map
            </button>
            <button
              className="btn secondary"
              onClick={() => navigateTo("/dashboard/revenue-integrity/incidents")}
            >
              View incidents
            </button>
            <button
              className="btn primary"
              onClick={() => completeStep("finish")}
            >
              Finish onboarding
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
