import { useEffect, useMemo, useState } from "react";
import {
  apiFetch,
  API_BASE,
  ACTIVE_TENANT_KEY,
  TOKEN_KEY,
  USERNAME_KEY,
  logAuditEvent,
} from "./api";

function parseQueryParam(name) {
  const params = new URLSearchParams(window.location.search || "");
  const value = params.get(name);
  return value ? value.trim() : "";
}

function navigateTo(path) {
  if (!path) return;
  window.history.pushState({}, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export default function LoginForm({ onLogin }) {
  const [mode, setMode] = useState("signin");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [tenant, setTenant] = useState("");
  const [referralCode, setReferralCode] = useState(() => parseQueryParam("ref"));
  const [affiliateCode, setAffiliateCode] = useState(() => parseQueryParam("aff"));
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [ssoStatus, setSsoStatus] = useState(null);

  const affiliateMeta = useMemo(() => {
    const params = new URLSearchParams(window.location.search || "");
    const source = params.get("utm_source");
    const medium = params.get("utm_medium");
    const campaign = params.get("utm_campaign");
    const payload = {};
    if (source) payload.utm_source = source;
    if (medium) payload.utm_medium = medium;
    if (campaign) payload.utm_campaign = campaign;
    return Object.keys(payload).length ? payload : null;
  }, []);

  useEffect(() => {
    if (mode !== "signin") {
      setSsoStatus(null);
      return undefined;
    }
    let ignore = false;
    const tenantValue = tenant.trim();
    if (!tenantValue) {
      setSsoStatus(null);
      return undefined;
    }
    const controller = new AbortController();
    fetch(
      `${API_BASE}/auth/oidc/status?tenant_id=${encodeURIComponent(tenantValue)}`,
      { signal: controller.signal }
    )
      .then((resp) => (resp.ok ? resp.json() : null))
      .then((data) => {
        if (!ignore) setSsoStatus(data);
      })
      .catch(() => {
        if (!ignore) setSsoStatus(null);
      });
    return () => {
      ignore = true;
      controller.abort();
    };
  }, [mode, tenant]);

  const loginAfterRegister = async (tenantSlug) => {
    const headers = { "Content-Type": "application/json" };
    if (tenantSlug) headers["X-Tenant-ID"] = tenantSlug;
    const resp = await apiFetch("/login", {
      method: "POST",
      headers,
      body: JSON.stringify({ username, password }),
      skipReauth: true,
    });
    if (!resp.ok) {
      throw new Error("Account created, but login failed. Please sign in.");
    }
    const data = await resp.json();
    localStorage.setItem(TOKEN_KEY, data.access_token);
    localStorage.setItem(USERNAME_KEY, username);
    if (tenantSlug) {
      localStorage.setItem(ACTIVE_TENANT_KEY, tenantSlug);
    }
    await logAuditEvent("user_login_success", username);
    navigateTo("/dashboard/onboarding");
    onLogin(data.access_token);
  };

  const handleSignIn = async () => {
    const headers = { "Content-Type": "application/json" };
    const tenantValue = tenant.trim();
    if (tenantValue) headers["X-Tenant-ID"] = tenantValue;
    const resp = await apiFetch("/login", {
      method: "POST",
      headers,
      body: JSON.stringify({ username, password }),
      skipReauth: true,
    });
    if (!resp.ok) {
      throw new Error(await resp.text());
    }
    const data = await resp.json();
    localStorage.setItem(TOKEN_KEY, data.access_token);
    localStorage.setItem(USERNAME_KEY, username);
    if (tenantValue) localStorage.setItem(ACTIVE_TENANT_KEY, tenantValue);
    await logAuditEvent("user_login_success", username);
    onLogin(data.access_token);
  };

  const handleSignUp = async () => {
    if (!username.trim()) {
      throw new Error("Username is required.");
    }
    if (password.length < 6) {
      throw new Error("Password must be at least 6 characters.");
    }
    if (password !== confirmPassword) {
      throw new Error("Passwords do not match.");
    }

    const payload = {
      username: username.trim(),
      password,
    };
    if (referralCode.trim()) payload.referral_code = referralCode.trim();
    if (affiliateCode.trim()) payload.affiliate_code = affiliateCode.trim();
    if (affiliateMeta) payload.affiliate_meta = affiliateMeta;

    const resp = await apiFetch("/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      skipReauth: true,
    });
    if (!resp.ok) {
      const detail = await resp.json().catch(() => null);
      throw new Error(detail?.detail || "Unable to create account");
    }
    const registration = await resp.json();
    const tenantSlug = registration?.active_tenant_slug || "";
    await logAuditEvent("user_register", username.trim());
    await loginAfterRegister(tenantSlug);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      if (mode === "signup") {
        await handleSignUp();
      } else {
        await handleSignIn();
      }
    } catch (err) {
      if (mode !== "signup") {
        await logAuditEvent("user_login_failure", username);
      }
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleSso = () => {
    const tenantValue = tenant.trim();
    if (!tenantValue) {
      setError("Enter your workspace to use SSO");
      return;
    }
    const nextPath = window.location.pathname || "/";
    const url = `${API_BASE}/auth/oidc/start?tenant_id=${encodeURIComponent(
      tenantValue
    )}&next=${encodeURIComponent(nextPath)}`;
    window.location.assign(url);
  };

  return (
    <div className="center" style={{ minHeight: "100vh", padding: "2rem" }}>
      <div className="card" style={{ width: "100%", maxWidth: 440 }}>
        <div className="card-header">
          <div className="brand">
            <span className="brand-mark" />
            APIShield+
          </div>
        </div>
        <h2 style={{ margin: 0, marginBottom: "0.5rem" }}>
          {mode === "signup" ? "Create account" : "Sign in"}
        </h2>
        <p className="subtle" style={{ marginTop: 0, marginBottom: "1rem" }}>
          {mode === "signup"
            ? "Create your workspace and start onboarding in minutes."
            : "Enter your credentials to access the dashboard."}
        </p>

        <div className="row" style={{ marginBottom: "1rem" }}>
          <button
            className={`btn secondary ${mode === "signin" ? "nav-tab active" : ""}`}
            type="button"
            onClick={() => {
              setMode("signin");
              setError(null);
            }}
          >
            Sign in
          </button>
          <button
            className={`btn secondary ${mode === "signup" ? "nav-tab active" : ""}`}
            type="button"
            onClick={() => {
              setMode("signup");
              setError(null);
            }}
          >
            Sign up
          </button>
        </div>

        <form className="form" onSubmit={handleSubmit}>
          <div className="field">
            <label className="label" htmlFor="auth-username">Username</label>
            <input
              id="auth-username"
              className="input"
              name="username"
              type="text"
              placeholder="alice"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
          </div>

          {mode === "signin" && (
            <div className="field">
              <label className="label" htmlFor="auth-tenant">Workspace</label>
              <input
                id="auth-tenant"
                className="input"
                name="tenant"
                type="text"
                placeholder="acme"
                value={tenant}
                onChange={(e) => setTenant(e.target.value)}
              />
            </div>
          )}

          <div className="field">
            <label className="label" htmlFor="auth-password">Password</label>
            <input
              id="auth-password"
              className="input"
              name="password"
              type="password"
              placeholder="********"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>

          {mode === "signup" && (
            <>
              <div className="field">
                <label className="label" htmlFor="auth-confirm-password">Confirm password</label>
                <input
                  id="auth-confirm-password"
                  className="input"
                  name="confirmPassword"
                  type="password"
                  placeholder="********"
                  required
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                />
              </div>
              <div className="field">
                <label className="label" htmlFor="auth-referral">Referral code (optional)</label>
                <input
                  id="auth-referral"
                  className="input"
                  name="referral"
                  type="text"
                  placeholder="REF-CODE"
                  value={referralCode}
                  onChange={(e) => setReferralCode(e.target.value)}
                />
              </div>
              <div className="field">
                <label className="label" htmlFor="auth-affiliate">Affiliate code (optional)</label>
                <input
                  id="auth-affiliate"
                  className="input"
                  name="affiliate"
                  type="text"
                  placeholder="AFF-CODE"
                  value={affiliateCode}
                  onChange={(e) => setAffiliateCode(e.target.value)}
                />
              </div>
            </>
          )}

          <button className="btn" type="submit" disabled={submitting}>
            {submitting
              ? mode === "signup"
                ? "Creating account..."
                : "Signing in..."
              : mode === "signup"
              ? "Create account"
              : "Sign in"}
          </button>
        </form>

        {mode === "signin" && ssoStatus?.enabled && (
          <button className="btn secondary" type="button" onClick={handleSso}>
            Sign in with SSO
          </button>
        )}

        {mode === "signin" && ssoStatus?.sso_required && (
          <p className="subtle" style={{ marginTop: "0.75rem" }}>
            This workspace requires SSO. Password login is disabled.
          </p>
        )}

        {error && <p style={{ color: "var(--danger)", marginTop: "1rem" }}>{error}</p>}
      </div>
    </div>
  );
}
