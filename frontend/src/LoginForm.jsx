import { useEffect, useState } from "react";
import { apiFetch, API_BASE, ACTIVE_TENANT_KEY, TOKEN_KEY, USERNAME_KEY, logAuditEvent } from "./api";

export default function LoginForm({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [tenant, setTenant] = useState("");
  const [error, setError] = useState(null);
  const [ssoStatus, setSsoStatus] = useState(null);

  useEffect(() => {
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
  }, [tenant]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    try {
      const headers = { "Content-Type": "application/json" };
      if (tenant.trim()) headers["X-Tenant-ID"] = tenant.trim();
      const resp = await apiFetch("/login", {
        method: "POST",
        headers,
        body: JSON.stringify({ username, password }),
        skipReauth: true,
      });
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      localStorage.setItem(TOKEN_KEY, data.access_token);
      localStorage.setItem(USERNAME_KEY, username);
      if (tenant.trim()) localStorage.setItem(ACTIVE_TENANT_KEY, tenant.trim());
      await logAuditEvent("user_login_success", username);
      onLogin(data.access_token);
    } catch (err) {
      await logAuditEvent("user_login_failure", username);
      setError(err.message);
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
      <div className="card" style={{ width: "100%", maxWidth: 420 }}>
        <div className="card-header"><div className="brand"><span className="brand-mark" />APIShield+</div></div>
        <h2 style={{ margin: 0, marginBottom: "0.5rem" }}>Sign in</h2>
        <p className="subtle" style={{ marginTop: 0, marginBottom: "1rem" }}>Enter your credentials to access the dashboard</p>
        <form className="form" onSubmit={handleSubmit}>
          <div className="field"><label className="label">Username</label>
            <input className="input" name="username" type="text" placeholder="alice" required value={username} onChange={(e) => setUsername(e.target.value)} />
          </div>
          <div className="field"><label className="label">Workspace</label>
            <input className="input" name="tenant" type="text" placeholder="acme" value={tenant} onChange={(e) => setTenant(e.target.value)} />
          </div>
          <div className="field"><label className="label">Password</label>
            <input className="input" name="password" type="password" placeholder="********" required value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          <button className="btn" type="submit">Sign in</button>
        </form>
        {ssoStatus?.enabled && (
          <button className="btn secondary" type="button" onClick={handleSso}>
            Sign in with SSO
          </button>
        )}
        {ssoStatus?.sso_required && (
          <p className="subtle" style={{ marginTop: "0.75rem" }}>
            This workspace requires SSO. Password login is disabled.
          </p>
        )}
        {error && (<p style={{ color: "var(--danger)", marginTop: "1rem" }}>{error}</p>)}
      </div>
    </div>
  );
}
