import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch, ACTIVE_TENANT_KEY } from "./api";
import { getRoleTemplate } from "./roles";
import PaywallCard from "./components/PaywallCard";
import PaywallModal from "./components/PaywallModal";

const TAB_OPTIONS = [
  { value: "channels", label: "Channels" },
  { value: "rules", label: "Rules" },
  { value: "history", label: "History" },
];

const CHANNEL_TYPES = [
  { value: "slack", label: "Slack (Webhook)" },
  { value: "webhook", label: "Webhook" },
  { value: "email", label: "Email" },
];

const TRIGGER_OPTIONS = [
  { value: "incident_created", label: "Incident created" },
  { value: "incident_severity_at_least", label: "Incident severity at least" },
  { value: "conversion_drop_over_threshold", label: "Conversion drop threshold" },
  { value: "login_fail_spike", label: "Login failure spike" },
  { value: "threat_spike", label: "Threat spike" },
  { value: "new_country_login", label: "New country login" },
  { value: "integrity_signal_detected", label: "Integrity signal detected" },
];

const CATEGORY_OPTIONS = [
  { value: "login", label: "Login" },
  { value: "threat", label: "Threat" },
  { value: "integrity", label: "Integrity" },
  { value: "bot", label: "Bot" },
  { value: "anomaly", label: "Anomaly" },
];

const SEVERITY_OPTIONS = [
  { value: "", label: "Any severity" },
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
  { value: "critical", label: "Critical" },
];

const HISTORY_RANGES = [
  { value: "24h", label: "Last 24 hours", days: 1 },
  { value: "7d", label: "Last 7 days", days: 7 },
  { value: "30d", label: "Last 30 days", days: 30 },
  { value: "all", label: "All time", days: null },
];


const buildTimeWindow = (days, now = new Date()) => {
  if (!days) return { from: null, to: null };
  const to = new Date(now);
  const from = new Date(now.getTime() - days * 24 * 60 * 60 * 1000);
  return { from, to };
};

const formatDateTime = (value) => {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--";
  return date.toLocaleString();
};

const parseCsvList = (value) =>
  (value || "")
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);

const parsePositiveNumber = (value) => {
  if (value === "" || value == null) return null;
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) return null;
  return parsed;
};

const parsePositiveInt = (value) => {
  const parsed = parsePositiveNumber(value);
  if (parsed == null) return null;
  return Math.round(parsed);
};

const extractDomain = (urlValue) => {
  if (!urlValue) return "";
  try {
    return new URL(urlValue).hostname || "";
  } catch (err) {
    return "";
  }
};

const defaultChannelForm = {
  id: null,
  type: "slack",
  name: "",
  isEnabled: true,
  slackWebhookUrl: "",
  slackChannel: "",
  webhookUrl: "",
  webhookSigningSecret: "",
  emailRecipients: "",
};

const defaultRuleForm = {
  name: "",
  triggerType: "incident_created",
  isEnabled: true,
  categories: [],
  severityMin: "",
  pathMatchers: "",
  countPerMinute: "",
  deltaPercent: "",
  lostRevenueMin: "",
  confidenceMin: "",
  cooldownSeconds: "",
  quietHoursTimezone: "",
  quietHoursRanges: "",
  channelIds: [],
};

export default function NotificationsSettingsPage() {
  const [activeTab, setActiveTab] = useState("channels");
  const [tenants, setTenants] = useState([]);
  const [activeTenant, setActiveTenant] = useState(
    localStorage.getItem(ACTIVE_TENANT_KEY) || ""
  );
  const [features, setFeatures] = useState({});
  const [limits, setLimits] = useState({});
  const [activeRole, setActiveRole] = useState(null);

  const [channels, setChannels] = useState([]);
  const [rules, setRules] = useState([]);
  const [deliveries, setDeliveries] = useState([]);

  const [channelsLoading, setChannelsLoading] = useState(false);
  const [rulesLoading, setRulesLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [channelsError, setChannelsError] = useState("");
  const [rulesError, setRulesError] = useState("");
  const [historyError, setHistoryError] = useState("");
  const [actionStatus, setActionStatus] = useState("");

  const [channelForm, setChannelForm] = useState(defaultChannelForm);
  const [ruleForm, setRuleForm] = useState(defaultRuleForm);
  const [ruleFormError, setRuleFormError] = useState("");
  const [channelFormError, setChannelFormError] = useState("");

  const [historyStatus, setHistoryStatus] = useState("");
  const [historyRange, setHistoryRange] = useState("7d");
  const [paywallConfig, setPaywallConfig] = useState(null);
  const roleTemplate = useMemo(() => getRoleTemplate(activeRole), [activeRole]);

  const canManage = useMemo(
    () =>
      ["owner", "admin", "security_admin"].includes(String(activeRole || "").toLowerCase()),
    [activeRole]
  );
  const advancedAlerting = Boolean(features.advanced_alerting);
  const channelLimit = parsePositiveInt(limits.notification_channels);
  const ruleLimit = parsePositiveInt(limits.notification_rules);
  const channelLimitReached = channelLimit != null && channels.length >= channelLimit;
  const ruleLimitReached = ruleLimit != null && rules.length >= ruleLimit;

  const openNotificationsPaywall = useCallback((source, overrides = {}) => {
    setPaywallConfig({
      title: "Upgrade notification automation",
      subtitle: "Unlock higher limits and advanced alerting workflows.",
      bullets: [
        "Conversion drop alerts and revenue leak notifications.",
        "Higher channel and rule limits per workspace.",
        "Advanced routing and webhook automation.",
      ],
      previewTitle: "Preview",
      preview: (
        <div className="paywall-preview-list">
          <div className="paywall-preview-row">
            <span>Conversion drop alert</span>
            <span>Pro</span>
          </div>
          <div className="paywall-preview-row">
            <span>Revenue leak workflow</span>
            <span>Pro</span>
          </div>
          <div className="paywall-preview-row">
            <span>Priority routing</span>
            <span>Business</span>
          </div>
        </div>
      ),
      featureKey: "advanced_alerting",
      source,
      planKey: "pro",
      ...overrides,
    });
  }, []);

  const closePaywall = useCallback(() => setPaywallConfig(null), []);

  const channelMap = useMemo(() => {
    const map = new Map();
    channels.forEach((channel) => {
      map.set(channel.id, channel);
    });
    return map;
  }, [channels]);

  const selectableChannels = useMemo(
    () => channels.filter((channel) => channel.is_enabled && channel.is_configured),
    [channels]
  );

  const historyRangeValue = useMemo(
    () => HISTORY_RANGES.find((range) => range.value === historyRange) || HISTORY_RANGES[1],
    [historyRange]
  );

  const loadTenants = useCallback(async () => {
    try {
      const resp = await apiFetch("/api/v1/tenants");
      if (!resp.ok) {
        throw new Error("Unable to load tenants");
      }
      const data = await resp.json();
      setTenants(Array.isArray(data) ? data : []);
      if (!activeTenant && data.length) {
        const first = data[0];
        setActiveTenant(first.slug);
        localStorage.setItem(ACTIVE_TENANT_KEY, String(first.slug));
      }
    } catch (err) {
      setActionStatus(err.message || "Unable to load tenants");
    }
  }, [activeTenant]);

  const loadEntitlements = useCallback(async () => {
    if (!activeTenant) return;
    try {
      const resp = await apiFetch("/api/v1/me", { skipReauth: true });
      if (!resp.ok) {
        throw new Error("Unable to load entitlements");
      }
      const data = await resp.json();
      const entitlements = data?.entitlements || {};
      setFeatures(entitlements.features || {});
      setLimits(entitlements.limits || {});
      setActiveRole(data?.active_role || null);
    } catch (err) {
      setFeatures({});
      setLimits({});
      setActiveRole(null);
    }
  }, [activeTenant]);

  const loadChannels = useCallback(async () => {
    if (!activeTenant) return;
    setChannelsLoading(true);
    setChannelsError("");
    try {
      const resp = await apiFetch("/api/v1/notifications/channels");
      if (!resp.ok) {
        throw new Error("Unable to load channels");
      }
      const data = await resp.json();
      setChannels(Array.isArray(data) ? data : []);
    } catch (err) {
      setChannels([]);
      setChannelsError(err.message || "Unable to load channels");
    } finally {
      setChannelsLoading(false);
    }
  }, [activeTenant]);

  const loadRules = useCallback(async () => {
    if (!activeTenant) return;
    setRulesLoading(true);
    setRulesError("");
    try {
      const resp = await apiFetch("/api/v1/notifications/rules");
      if (!resp.ok) {
        throw new Error("Unable to load rules");
      }
      const data = await resp.json();
      setRules(Array.isArray(data) ? data : []);
    } catch (err) {
      setRules([]);
      setRulesError(err.message || "Unable to load rules");
    } finally {
      setRulesLoading(false);
    }
  }, [activeTenant]);

  const loadHistory = useCallback(async () => {
    if (!activeTenant) return;
    setHistoryLoading(true);
    setHistoryError("");
    try {
      const params = new URLSearchParams();
      if (historyStatus) params.set("status", historyStatus);
      if (historyRangeValue.days) {
        const { from, to } = buildTimeWindow(historyRangeValue.days, new Date());
        if (from && to) {
          params.set("from", from.toISOString());
          params.set("to", to.toISOString());
        }
      }
      const resp = await apiFetch(`/api/v1/notifications/deliveries?${params.toString()}`);
      if (!resp.ok) {
        throw new Error("Unable to load delivery history");
      }
      const data = await resp.json();
      setDeliveries(Array.isArray(data) ? data : []);
    } catch (err) {
      setDeliveries([]);
      setHistoryError(err.message || "Unable to load delivery history");
    } finally {
      setHistoryLoading(false);
    }
  }, [activeTenant, historyRangeValue.days, historyStatus]);

  useEffect(() => {
    loadTenants();
  }, [loadTenants]);

  useEffect(() => {
    if (!activeTenant) {
      localStorage.removeItem(ACTIVE_TENANT_KEY);
      setChannels([]);
      setRules([]);
      setDeliveries([]);
      setFeatures({});
      setLimits({});
      setActiveRole(null);
      return;
    }
    localStorage.setItem(ACTIVE_TENANT_KEY, activeTenant);
    loadEntitlements();
    loadChannels();
    loadRules();
  }, [activeTenant, loadChannels, loadEntitlements, loadRules]);

  useEffect(() => {
    if (activeTab === "history") {
      loadHistory();
    }
  }, [activeTab, loadHistory]);

  const resetChannelForm = () => {
    setChannelForm(defaultChannelForm);
    setChannelFormError("");
  };

  const resetRuleForm = () => {
    setRuleForm(defaultRuleForm);
    setRuleFormError("");
  };

  const handleChannelSubmit = async (event) => {
    event.preventDefault();
    if (!canManage) {
      setChannelFormError("Owner, admin, or security admin role required to manage channels.");
      return;
    }
    if (!channelForm.name.trim()) {
      setChannelFormError("Channel name is required.");
      return;
    }
    if (channelForm.id == null && channelLimitReached) {
      setChannelFormError("Channel limit reached for your plan.");
      openNotificationsPaywall("notifications_channel_limit");
      return;
    }

    const channelType = channelForm.type;
    if (channelType === "webhook" && !advancedAlerting) {
      setChannelFormError("Webhook channels require a Pro plan.");
      openNotificationsPaywall("notifications_webhook_lock");
      return;
    }

    const payload = {
      name: channelForm.name.trim(),
      is_enabled: Boolean(channelForm.isEnabled),
    };

    let configPublic = {};
    let configSecret = null;

    if (channelType === "slack") {
      if (!channelForm.slackWebhookUrl.trim() && channelForm.id == null) {
        setChannelFormError("Slack webhook URL is required.");
        return;
      }
      if (channelForm.slackChannel.trim()) {
        configPublic.channel = channelForm.slackChannel.trim();
      }
      if (channelForm.slackWebhookUrl.trim()) {
        configSecret = { webhook_url: channelForm.slackWebhookUrl.trim() };
      }
    } else if (channelType === "webhook") {
      if (!channelForm.webhookUrl.trim() && channelForm.id == null) {
        setChannelFormError("Webhook URL is required.");
        return;
      }
      const webhookUrl = channelForm.webhookUrl.trim();
      if (webhookUrl) {
        configPublic.domain = extractDomain(webhookUrl);
        configSecret = { url: webhookUrl };
        if (channelForm.webhookSigningSecret.trim()) {
          configSecret.signing_secret = channelForm.webhookSigningSecret.trim();
        }
      }
    } else if (channelType === "email") {
      const recipients = parseCsvList(channelForm.emailRecipients);
      if (recipients.length) {
        configPublic.recipients = recipients;
      }
    }

    payload.config_public_json = Object.keys(configPublic).length ? configPublic : null;
    if (configSecret) {
      payload.config_secret = configSecret;
    }

    try {
      const resp = await apiFetch(
        channelForm.id == null
          ? "/api/v1/notifications/channels"
          : `/api/v1/notifications/channels/${channelForm.id}`,
        {
          method: channelForm.id == null ? "POST" : "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(
            channelForm.id == null ? { ...payload, type: channelType } : payload
          ),
        }
      );
      if (!resp.ok) {
        const detail = await resp.json().catch(() => null);
        throw new Error(detail?.detail || "Unable to save channel");
      }
      await loadChannels();
      resetChannelForm();
      setActionStatus("Channel saved.");
    } catch (err) {
      setChannelFormError(err.message || "Unable to save channel");
    }
  };

  const handleEditChannel = (channel) => {
    setChannelForm({
      id: channel.id,
      type: channel.type,
      name: channel.name || "",
      isEnabled: channel.is_enabled,
      slackWebhookUrl: "",
      slackChannel: channel.config_public_json?.channel || "",
      webhookUrl: "",
      webhookSigningSecret: "",
      emailRecipients: Array.isArray(channel.config_public_json?.recipients)
        ? channel.config_public_json.recipients.join(", ")
        : "",
    });
    setChannelFormError("");
    setActiveTab("channels");
  };

  const handleDeleteChannel = async (channelId) => {
    if (!canManage) return;
    try {
      const resp = await apiFetch(`/api/v1/notifications/channels/${channelId}`, {
        method: "DELETE",
      });
      if (!resp.ok) {
        throw new Error("Unable to disable channel");
      }
      await loadChannels();
      setActionStatus("Channel disabled.");
    } catch (err) {
      setChannelsError(err.message || "Unable to disable channel");
    }
  };

  const handleToggleChannel = async (channel) => {
    if (!canManage) return;
    try {
      const resp = await apiFetch(`/api/v1/notifications/channels/${channel.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_enabled: !channel.is_enabled }),
      });
      if (!resp.ok) {
        throw new Error("Unable to update channel");
      }
      await loadChannels();
    } catch (err) {
      setChannelsError(err.message || "Unable to update channel");
    }
  };

  const handleTestChannel = async (channelId) => {
    if (!canManage) return;
    setActionStatus("");
    try {
      const resp = await apiFetch(`/api/v1/notifications/channels/${channelId}/test`, {
        method: "POST",
      });
      if (!resp.ok) {
        const detail = await resp.json().catch(() => null);
        throw new Error(detail?.detail || "Test send failed");
      }
      await loadChannels();
      setActionStatus("Test notification sent.");
    } catch (err) {
      setChannelsError(err.message || "Test send failed");
    }
  };

  const handleRuleSubmit = async (event) => {
    event.preventDefault();
    if (!canManage) {
      setRuleFormError("Owner, admin, or security admin role required to manage rules.");
      return;
    }
    if (!ruleForm.name.trim()) {
      setRuleFormError("Rule name is required.");
      return;
    }
    if (ruleLimitReached) {
      setRuleFormError("Rule limit reached for your plan.");
      openNotificationsPaywall("notifications_rule_limit");
      return;
    }
    if (!ruleForm.channelIds.length) {
      setRuleFormError("Select at least one channel.");
      return;
    }

    const requiresSeverity = ruleForm.triggerType === "incident_severity_at_least";
    const requiresConversion = ruleForm.triggerType === "conversion_drop_over_threshold";
    const requiresCount = ["login_fail_spike", "threat_spike", "integrity_signal_detected"].includes(
      ruleForm.triggerType
    );

    if (requiresSeverity && !ruleForm.severityMin) {
      setRuleFormError("Minimum severity is required for this trigger.");
      return;
    }
    if (requiresConversion && !advancedAlerting) {
      setRuleFormError("Conversion drop alerts require a Pro plan.");
      openNotificationsPaywall("notifications_conversion_alert");
      return;
    }
    if (requiresConversion) {
      const deltaValue = parsePositiveNumber(ruleForm.deltaPercent);
      const revenueValue = parsePositiveNumber(ruleForm.lostRevenueMin);
      if (!deltaValue && !revenueValue) {
        setRuleFormError("Provide delta percent or lost revenue threshold.");
        return;
      }
    }
    if (requiresCount && !parsePositiveInt(ruleForm.countPerMinute)) {
      setRuleFormError("Count per minute is required for this trigger.");
      return;
    }

    const filters = {};
    if (ruleForm.categories.length) filters.categories = ruleForm.categories;
    if (ruleForm.severityMin) filters.severity_min = ruleForm.severityMin;
    const paths = parseCsvList(ruleForm.pathMatchers);
    if (paths.length) filters.path_matchers = paths;

    const thresholds = {};
    const countValue = parsePositiveInt(ruleForm.countPerMinute);
    if (countValue) thresholds.count_per_minute = countValue;
    const deltaValue = parsePositiveNumber(ruleForm.deltaPercent);
    if (deltaValue) thresholds.delta_percent = deltaValue;
    const revenueValue = parsePositiveNumber(ruleForm.lostRevenueMin);
    if (revenueValue) thresholds.lost_revenue_min = revenueValue;
    const confidenceValue = parsePositiveNumber(ruleForm.confidenceMin);
    if (confidenceValue != null) thresholds.confidence_min = confidenceValue;
    const cooldownValue = parsePositiveInt(ruleForm.cooldownSeconds);
    if (cooldownValue) thresholds.cooldown_seconds = cooldownValue;

    const quietHours = {};
    const quietTimezone = ruleForm.quietHoursTimezone.trim();
    const quietRanges = parseCsvList(ruleForm.quietHoursRanges);
    if (quietTimezone && quietRanges.length) {
      quietHours.timezone = quietTimezone;
      quietHours.ranges = quietRanges;
    }

    const payload = {
      name: ruleForm.name.trim(),
      trigger_type: ruleForm.triggerType,
      is_enabled: Boolean(ruleForm.isEnabled),
      route_to_channel_ids: ruleForm.channelIds,
      filters_json: Object.keys(filters).length ? filters : null,
      thresholds_json: Object.keys(thresholds).length ? thresholds : null,
      quiet_hours_json: Object.keys(quietHours).length ? quietHours : null,
    };

    try {
      const resp = await apiFetch("/api/v1/notifications/rules", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!resp.ok) {
        const detail = await resp.json().catch(() => null);
        throw new Error(detail?.detail || "Unable to create rule");
      }
      await loadRules();
      resetRuleForm();
      setActionStatus("Rule created.");
    } catch (err) {
      setRuleFormError(err.message || "Unable to create rule");
    }
  };

  const handleToggleRule = async (rule) => {
    if (!canManage) return;
    try {
      const resp = await apiFetch(`/api/v1/notifications/rules/${rule.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_enabled: !rule.is_enabled }),
      });
      if (!resp.ok) {
        throw new Error("Unable to update rule");
      }
      await loadRules();
    } catch (err) {
      setRulesError(err.message || "Unable to update rule");
    }
  };

  return (
    <div className="stack">
      <section className="card notifications-header">
        <div>
          <h2 className="section-title">Notifications</h2>
          <p className="subtle">
            Configure alert channels, routing rules, and delivery history.
          </p>
          {activeRole && (
            <div className="help" title={roleTemplate?.description || ""}>
              Role: {roleTemplate?.label || activeRole}
            </div>
          )}
        </div>
        <div className="notifications-tenant">
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

      <section className="card">
        <div className="notifications-tabs">
          {TAB_OPTIONS.map((tab) => (
            <button
              key={tab.value}
              className={`btn secondary ${activeTab === tab.value ? "active" : ""}`}
              onClick={() => setActiveTab(tab.value)}
            >
              {tab.label}
            </button>
          ))}
        </div>
        {actionStatus && <div className="help">{actionStatus}</div>}
      </section>

      {activeTab === "channels" && (
        <>
          {(channelLimitReached || !advancedAlerting) && (
            <PaywallCard
              title="Upgrade for advanced notifications"
              subtitle="Add webhooks and scale alert channels across teams."
              bullets={[
                !advancedAlerting ? "Webhook integrations" : null,
                channelLimitReached ? "Higher channel limits" : null,
              ].filter(Boolean)}
              previewTitle="Preview"
              preview={
                <div className="paywall-preview-list">
                  <div className="paywall-preview-row">
                    <span>Slack + Webhook</span>
                    <span>Pro</span>
                  </div>
                  <div className="paywall-preview-row">
                    <span>Unlimited channels</span>
                    <span>Business</span>
                  </div>
                </div>
              }
              featureKey="advanced_alerting"
              source="notifications_channels_card"
              planKey="pro"
              showDismiss={false}
              className="card"
            />
          )}

          <section className="notifications-grid">
            <div className="card">
              <div className="notifications-table-header">
                <div>
                  <h3 className="section-title">Channels</h3>
                  <div className="subtle">
                    {channels.length ? `${channels.length} channels` : "No channels yet."}
                  </div>
                </div>
              </div>
              {channelsLoading && <p className="subtle">Loading channels...</p>}
              {channelsError && <p className="error-text">{channelsError}</p>}
              {!channelsLoading && !channelsError && channels.length === 0 && (
                <p className="subtle">Create your first channel to start sending alerts.</p>
              )}
              {!channelsLoading && !channelsError && channels.length > 0 && (
                <table className="table notifications-table">
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Type</th>
                      <th>Status</th>
                      <th>Configured</th>
                      <th>Last tested</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {channels.map((channel) => (
                      <tr key={channel.id}>
                        <td>
                          <div>{channel.name}</div>
                          {channel.last_error && (
                            <div className="help">Last error: {channel.last_error}</div>
                          )}
                        </td>
                        <td>{channel.type}</td>
                        <td>
                          <span className={`status-chip ${channel.is_enabled ? "enabled" : "disabled"}`}>
                            {channel.is_enabled ? "Enabled" : "Disabled"}
                          </span>
                        </td>
                        <td>{channel.is_configured ? "Yes" : "Missing secret"}</td>
                        <td>{formatDateTime(channel.last_tested_at)}</td>
                        <td>
                          <div className="notifications-actions">
                            <button
                              className="btn secondary small"
                              onClick={() => handleEditChannel(channel)}
                              disabled={!canManage}
                            >
                              Edit
                            </button>
                            <button
                              className="btn secondary small"
                              onClick={() => handleToggleChannel(channel)}
                              disabled={!canManage}
                            >
                              {channel.is_enabled ? "Disable" : "Enable"}
                            </button>
                            <button
                              className="btn secondary small"
                              onClick={() => handleTestChannel(channel.id)}
                              disabled={!canManage || !channel.is_configured}
                            >
                              Test
                            </button>
                            <button
                              className="btn secondary small"
                              onClick={() => handleDeleteChannel(channel.id)}
                              disabled={!canManage}
                            >
                              Remove
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            <div className="card notifications-form-card">
              <div className="panel-header">
                <h3 className="section-title">
                  {channelForm.id ? "Edit channel" : "Create channel"}
                </h3>
                {channelLimit != null && (
                  <div className="help">
                    {channels.length}/{channelLimit} channels used
                  </div>
                )}
              </div>
              {!canManage && (
                <div className="locked-panel">
                  Only owner, admin, or security admin roles can manage channels.
                </div>
              )}
              <form className="notifications-form" onSubmit={handleChannelSubmit}>
                <div className="field">
                  <label className="label">Channel type</label>
                  <select
                    className="select"
                    value={channelForm.type}
                    onChange={(e) =>
                      setChannelForm((prev) => ({ ...prev, type: e.target.value }))
                    }
                    disabled={channelForm.id != null}
                  >
                    {CHANNEL_TYPES.map((option) => (
                      <option
                        key={option.value}
                        value={option.value}
                        disabled={option.value === "webhook" && !advancedAlerting}
                      >
                        {option.value === "webhook" && !advancedAlerting
                          ? `${option.label} (Pro)`
                          : option.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label className="label">Name</label>
                  <input
                    className="input"
                    value={channelForm.name}
                    onChange={(e) =>
                      setChannelForm((prev) => ({ ...prev, name: e.target.value }))
                    }
                    placeholder="Ops Slack"
                  />
                </div>
                {channelForm.type === "slack" && (
                  <>
                    <div className="field">
                      <label className="label">Slack webhook URL</label>
                      <input
                        className="input"
                        value={channelForm.slackWebhookUrl}
                        onChange={(e) =>
                          setChannelForm((prev) => ({
                            ...prev,
                            slackWebhookUrl: e.target.value,
                          }))
                        }
                        placeholder="https://hooks.slack.com/services/..."
                      />
                    </div>
                    <div className="field">
                      <label className="label">Slack channel (optional)</label>
                      <input
                        className="input"
                        value={channelForm.slackChannel}
                        onChange={(e) =>
                          setChannelForm((prev) => ({
                            ...prev,
                            slackChannel: e.target.value,
                          }))
                        }
                        placeholder="#security"
                      />
                    </div>
                  </>
                )}
                {channelForm.type === "webhook" && (
                  <>
                    <div className="field">
                      <label className="label">Webhook URL</label>
                      <input
                        className="input"
                        value={channelForm.webhookUrl}
                        onChange={(e) =>
                          setChannelForm((prev) => ({
                            ...prev,
                            webhookUrl: e.target.value,
                          }))
                        }
                        placeholder="https://hooks.example.com/notify"
                      />
                    </div>
                    <div className="field">
                      <label className="label">Signing secret (optional)</label>
                      <input
                        className="input"
                        value={channelForm.webhookSigningSecret}
                        onChange={(e) =>
                          setChannelForm((prev) => ({
                            ...prev,
                            webhookSigningSecret: e.target.value,
                          }))
                        }
                        placeholder="shared secret"
                      />
                    </div>
                  </>
                )}
                {channelForm.type === "email" && (
                  <div className="field">
                    <label className="label">Recipients</label>
                    <input
                      className="input"
                      value={channelForm.emailRecipients}
                      onChange={(e) =>
                        setChannelForm((prev) => ({
                          ...prev,
                          emailRecipients: e.target.value,
                        }))
                      }
                      placeholder="sec@company.com, ops@company.com"
                    />
                  </div>
                )}
                <div className="field">
                  <label className="label">Enabled</label>
                  <select
                    className="select"
                    value={channelForm.isEnabled ? "yes" : "no"}
                    onChange={(e) =>
                      setChannelForm((prev) => ({
                        ...prev,
                        isEnabled: e.target.value === "yes",
                      }))
                    }
                  >
                    <option value="yes">Enabled</option>
                    <option value="no">Disabled</option>
                  </select>
                </div>
                {channelFormError && <div className="error-text">{channelFormError}</div>}
                <div className="row">
                  <button
                    className="btn primary"
                    type="submit"
                    disabled={!canManage || (channelLimitReached && channelForm.id == null)}
                  >
                    {channelForm.id ? "Update channel" : "Create channel"}
                  </button>
                  <button className="btn secondary" type="button" onClick={resetChannelForm}>
                    Clear
                  </button>
                </div>
              </form>
            </div>
          </section>
        </>
      )}

      {activeTab === "rules" && (
        <>
          {(ruleLimitReached || !advancedAlerting) && (
            <PaywallCard
              title="Upgrade for advanced rules"
              subtitle="Pro unlocks conversion alerts and higher rule limits."
              bullets={[
                !advancedAlerting ? "Conversion drop alerts" : null,
                ruleLimitReached ? "Higher rule limits for alerting" : null,
              ].filter(Boolean)}
              previewTitle="Preview"
              preview={
                <div className="paywall-preview-list">
                  <div className="paywall-preview-row">
                    <span>Conversion drop alert</span>
                    <span>Pro</span>
                  </div>
                  <div className="paywall-preview-row">
                    <span>Revenue leak threshold</span>
                    <span>Pro</span>
                  </div>
                </div>
              }
              featureKey="advanced_alerting"
              source="notifications_rules_card"
              planKey="pro"
              showDismiss={false}
              className="card"
            />
          )}

          <section className="notifications-grid">
            <div className="card">
              <div className="notifications-table-header">
                <div>
                  <h3 className="section-title">Rules</h3>
                  <div className="subtle">
                    {rules.length ? `${rules.length} rules` : "No rules yet."}
                  </div>
                </div>
              </div>
              {rulesLoading && <p className="subtle">Loading rules...</p>}
              {rulesError && <p className="error-text">{rulesError}</p>}
              {!rulesLoading && !rulesError && rules.length === 0 && (
                <p className="subtle">Create rules to route alerts to channels.</p>
              )}
              {!rulesLoading && !rulesError && rules.length > 0 && (
                <table className="table notifications-table">
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Trigger</th>
                      <th>Channels</th>
                      <th>Status</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {rules.map((rule) => (
                      <tr key={rule.id}>
                        <td>{rule.name}</td>
                        <td>{rule.trigger_type}</td>
                        <td>
                          {(rule.route_to_channel_ids || [])
                            .map((id) => channelMap.get(id)?.name || `Channel ${id}`)
                            .join(", ") || "--"}
                        </td>
                        <td>
                          <span className={`status-chip ${rule.is_enabled ? "enabled" : "disabled"}`}>
                            {rule.is_enabled ? "Enabled" : "Disabled"}
                          </span>
                        </td>
                        <td>
                          <button
                            className="btn secondary small"
                            onClick={() => handleToggleRule(rule)}
                            disabled={!canManage}
                          >
                            {rule.is_enabled ? "Disable" : "Enable"}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            <div className="card notifications-form-card">
              <div className="panel-header">
                <h3 className="section-title">Create rule</h3>
                {ruleLimit != null && (
                  <div className="help">
                    {rules.length}/{ruleLimit} rules used
                  </div>
                )}
              </div>
              {!canManage && (
                <div className="locked-panel">
                  Only owner, admin, or security admin roles can manage rules.
                </div>
              )}
              <form className="notifications-form" onSubmit={handleRuleSubmit}>
                <div className="field">
                  <label className="label">Rule name</label>
                  <input
                    className="input"
                    value={ruleForm.name}
                    onChange={(e) =>
                      setRuleForm((prev) => ({ ...prev, name: e.target.value }))
                    }
                    placeholder="Critical incidents"
                  />
                </div>
                <div className="field">
                  <label className="label">Trigger</label>
                  <select
                    className="select"
                    value={ruleForm.triggerType}
                    onChange={(e) =>
                      setRuleForm((prev) => ({ ...prev, triggerType: e.target.value }))
                    }
                  >
                    {TRIGGER_OPTIONS.map((option) => (
                      <option
                        key={option.value}
                        value={option.value}
                        disabled={
                          option.value === "conversion_drop_over_threshold" &&
                          !advancedAlerting
                        }
                      >
                        {option.value === "conversion_drop_over_threshold" && !advancedAlerting
                          ? `${option.label} (Pro)`
                          : option.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label className="label">Channels</label>
                  {selectableChannels.length ? (
                    <div className="notifications-checkboxes">
                      {selectableChannels.map((channel) => (
                        <label key={channel.id} className="notifications-checkbox">
                          <input
                            type="checkbox"
                            checked={ruleForm.channelIds.includes(channel.id)}
                            onChange={(e) => {
                              const selected = new Set(ruleForm.channelIds);
                              if (e.target.checked) selected.add(channel.id);
                              else selected.delete(channel.id);
                              setRuleForm((prev) => ({
                                ...prev,
                                channelIds: Array.from(selected),
                              }));
                            }}
                          />
                          <span>{channel.name}</span>
                        </label>
                      ))}
                    </div>
                  ) : (
                    <div className="help">No enabled channels are configured yet.</div>
                  )}
                </div>
                <div className="field">
                  <label className="label">Categories (optional)</label>
                  <div className="notifications-checkboxes">
                    {CATEGORY_OPTIONS.map((category) => (
                      <label key={category.value} className="notifications-checkbox">
                        <input
                          type="checkbox"
                          checked={ruleForm.categories.includes(category.value)}
                          onChange={(e) => {
                            const selected = new Set(ruleForm.categories);
                            if (e.target.checked) selected.add(category.value);
                            else selected.delete(category.value);
                            setRuleForm((prev) => ({
                              ...prev,
                              categories: Array.from(selected),
                            }));
                          }}
                        />
                        <span>{category.label}</span>
                      </label>
                    ))}
                  </div>
                </div>
                <div className="field">
                  <label className="label">Minimum severity</label>
                  <select
                    className="select"
                    value={ruleForm.severityMin}
                    onChange={(e) =>
                      setRuleForm((prev) => ({ ...prev, severityMin: e.target.value }))
                    }
                  >
                    {SEVERITY_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label className="label">Path matchers (optional)</label>
                  <input
                    className="input"
                    value={ruleForm.pathMatchers}
                    onChange={(e) =>
                      setRuleForm((prev) => ({ ...prev, pathMatchers: e.target.value }))
                    }
                    placeholder="/checkout*, /login"
                  />
                </div>
                <div className="field">
                  <label className="label">Count per minute</label>
                  <input
                    className="input"
                    type="number"
                    value={ruleForm.countPerMinute}
                    onChange={(e) =>
                      setRuleForm((prev) => ({ ...prev, countPerMinute: e.target.value }))
                    }
                    placeholder="60"
                  />
                </div>
                <div className="field">
                  <label className="label">Delta percent</label>
                  <input
                    className="input"
                    type="number"
                    value={ruleForm.deltaPercent}
                    onChange={(e) =>
                      setRuleForm((prev) => ({ ...prev, deltaPercent: e.target.value }))
                    }
                    placeholder="25"
                  />
                </div>
                <div className="field">
                  <label className="label">Lost revenue minimum</label>
                  <input
                    className="input"
                    type="number"
                    value={ruleForm.lostRevenueMin}
                    onChange={(e) =>
                      setRuleForm((prev) => ({ ...prev, lostRevenueMin: e.target.value }))
                    }
                    placeholder="500"
                  />
                </div>
                <div className="field">
                  <label className="label">Confidence minimum</label>
                  <input
                    className="input"
                    type="number"
                    value={ruleForm.confidenceMin}
                    onChange={(e) =>
                      setRuleForm((prev) => ({ ...prev, confidenceMin: e.target.value }))
                    }
                    placeholder="0.6"
                  />
                </div>
                <div className="field">
                  <label className="label">Cooldown seconds</label>
                  <input
                    className="input"
                    type="number"
                    value={ruleForm.cooldownSeconds}
                    onChange={(e) =>
                      setRuleForm((prev) => ({ ...prev, cooldownSeconds: e.target.value }))
                    }
                    placeholder="900"
                  />
                </div>
                <div className="field">
                  <label className="label">Quiet hours timezone</label>
                  <input
                    className="input"
                    value={ruleForm.quietHoursTimezone}
                    onChange={(e) =>
                      setRuleForm((prev) => ({
                        ...prev,
                        quietHoursTimezone: e.target.value,
                      }))
                    }
                    placeholder="UTC"
                  />
                </div>
                <div className="field">
                  <label className="label">Quiet hours ranges</label>
                  <input
                    className="input"
                    value={ruleForm.quietHoursRanges}
                    onChange={(e) =>
                      setRuleForm((prev) => ({
                        ...prev,
                        quietHoursRanges: e.target.value,
                      }))
                    }
                    placeholder="22:00-07:00"
                  />
                </div>
                <div className="field">
                  <label className="label">Enabled</label>
                  <select
                    className="select"
                    value={ruleForm.isEnabled ? "yes" : "no"}
                    onChange={(e) =>
                      setRuleForm((prev) => ({
                        ...prev,
                        isEnabled: e.target.value === "yes",
                      }))
                    }
                  >
                    <option value="yes">Enabled</option>
                    <option value="no">Disabled</option>
                  </select>
                </div>
                {ruleFormError && <div className="error-text">{ruleFormError}</div>}
                <div className="row">
                  <button
                    className="btn primary"
                    type="submit"
                    disabled={!canManage || ruleLimitReached}
                  >
                    Create rule
                  </button>
                  <button className="btn secondary" type="button" onClick={resetRuleForm}>
                    Clear
                  </button>
                </div>
              </form>
            </div>
          </section>
        </>
      )}

      {activeTab === "history" && (
        <section className="card">
          <div className="notifications-table-header">
            <div>
              <h3 className="section-title">Delivery history</h3>
              <div className="subtle">
                {deliveries.length ? `${deliveries.length} deliveries` : "No deliveries yet."}
              </div>
            </div>
            <div className="notifications-history-filters">
              <div className="field">
                <label className="label">Status</label>
                <select
                  className="select"
                  value={historyStatus}
                  onChange={(e) => setHistoryStatus(e.target.value)}
                >
                  <option value="">Any</option>
                  <option value="queued">Queued</option>
                  <option value="sent">Sent</option>
                  <option value="failed">Failed</option>
                  <option value="skipped">Skipped</option>
                </select>
              </div>
              <div className="field">
                <label className="label">Range</label>
                <select
                  className="select"
                  value={historyRange}
                  onChange={(e) => setHistoryRange(e.target.value)}
                >
                  {HISTORY_RANGES.map((range) => (
                    <option key={range.value} value={range.value}>
                      {range.label}
                    </option>
                  ))}
                </select>
              </div>
              <button className="btn secondary" onClick={loadHistory}>
                Refresh
              </button>
            </div>
          </div>
          {historyLoading && <p className="subtle">Loading history...</p>}
          {historyError && <p className="error-text">{historyError}</p>}
          {!historyLoading && !historyError && deliveries.length === 0 && (
            <p className="subtle">No delivery records for this time window.</p>
          )}
          {!historyLoading && !historyError && deliveries.length > 0 && (
            <table className="table notifications-table">
              <thead>
                <tr>
                  <th>Event</th>
                  <th>Status</th>
                  <th>Channel</th>
                  <th>Rule</th>
                  <th>Created</th>
                  <th>Sent</th>
                  <th>Attempts</th>
                </tr>
              </thead>
              <tbody>
                {deliveries.map((delivery) => {
                  const payload = delivery.payload_json || {};
                  return (
                    <tr key={delivery.id}>
                      <td>{payload.title || payload.type || "Notification"}</td>
                      <td>
                        <span className={`status-chip ${delivery.status || "open"}`}>
                          {delivery.status}
                        </span>
                        {delivery.error_message && (
                          <div className="help">Error: {delivery.error_message}</div>
                        )}
                      </td>
                      <td>{channelMap.get(delivery.channel_id)?.name || delivery.channel_id}</td>
                      <td>
                        {rules.find((rule) => rule.id === delivery.rule_id)?.name ||
                          delivery.rule_id}
                      </td>
                      <td>{formatDateTime(delivery.created_at)}</td>
                      <td>{formatDateTime(delivery.sent_at)}</td>
                      <td>{delivery.attempt_count}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </section>
      )}
      <PaywallModal
        open={Boolean(paywallConfig)}
        onClose={closePaywall}
        {...(paywallConfig || {})}
      />
    </div>
  );
}
