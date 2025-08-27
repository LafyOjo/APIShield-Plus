import { useState } from "react";
import { apiFetch, TOKEN_KEY, USERNAME_KEY, logAuditEvent } from "./api";

export default function LoginForm({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    try {
      const resp = await apiFetch("/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
        skipReauth: true,
      });
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      localStorage.setItem(TOKEN_KEY, data.access_token);
      localStorage.setItem(USERNAME_KEY, username);
      await logAuditEvent("user_login_success", username);
      onLogin(data.access_token);
    } catch (err) {
      await logAuditEvent("user_login_failure", username);
      setError(err.message);
    }
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
          <div className="field"><label className="label">Password</label>
            <input className="input" name="password" type="password" placeholder="••••••••" required value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          <button className="btn" type="submit">Sign in</button>
        </form>
        {error && (<p style={{ color: "var(--danger)", marginTop: "1rem" }}>{error}</p>)}
      </div>
    </div>
  );
}