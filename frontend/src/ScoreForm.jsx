import { useState, useEffect } from "react";
import { apiFetch } from "./api";

const DEFAULT_THRESHOLD = 5;

export default function ScoreForm({ token, onNewAlert }) {
  const [ip, setIp] = useState("");
  const [result, setResult] = useState("success");
  const [error, setError] = useState(null);
  const [warning, setWarning] = useState(null);
  const [threshold, setThreshold] = useState(DEFAULT_THRESHOLD);
  const [chain, setChain] = useState(null);
  const [isAdmin, setIsAdmin] = useState(false);

  const fetchChain = async () => {
    try {
      const resp = await apiFetch("/api/security/chain", { skipReauth: true });
      if (resp.status === 401 || resp.status === 403) {
        setWarning("Admin token required to fetch security chain");
        return;
      }
      if (resp.ok) {
        const data = await resp.json();
        setChain(data.chain);
      }
    } catch (err) {
      console.error("Failed to fetch chain", err);
    }
  };

  useEffect(() => {
    const verifyAdmin = async () => {
      if (!token) {
        setWarning("Admin token required to fetch settings");
        return;
      }
      try {
        const resp = await apiFetch("/api/me", { skipReauth: true });
        if (!resp.ok) {
          if (resp.status === 401 || resp.status === 403) {
            setWarning("Admin token required to fetch settings");
          }
          return;
        }
        const data = await resp.json();
        if (data.role !== "admin") {
          setWarning("Admin token required to fetch settings");
          return;
        }
        setIsAdmin(true);
        await fetchConfig();
        await fetchChain();
      } catch (err) {
        console.error("Failed to verify admin token", err);
      }
    };

    const fetchConfig = async () => {
      try {
        const resp = await apiFetch("/config", { skipReauth: true });
        if (resp.status === 401 || resp.status === 403) {
          setWarning("Admin token required to fetch config");
          return;
        }
        if (resp.ok) {
          const data = await resp.json();
          if (data.fail_limit) {
            setThreshold(data.fail_limit);
          }
        }
      } catch (err) {
        console.error("Failed to fetch config", err);
      }
    };

    verifyAdmin();
  }, [token]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    try {
      const headers = { "Content-Type": "application/json" };
      if (chain) headers["X-Chain-Password"] = chain;

      const resp = await apiFetch("/score", {
        method: "POST",
        headers,
        body: JSON.stringify({
          client_ip: ip,
          auth_result: result,
          with_jwt: Boolean(token),
        }),
        // <-- user-initiated action: prompt before the request
        forceReauth: true,
      });

      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();

      if (data.fails_last_minute > threshold) onNewAlert?.();
      if (isAdmin) await fetchChain();
    } catch (err) {
      setError(err.message);
      if (isAdmin) fetchChain();
    }
  };

  return (
    <form onSubmit={handleSubmit} className="score-form">
      <label>
        Client IP:
        <input
          type="text"
          placeholder="e.g. 10.0.0.1"
          value={ip}
          onChange={(e) => setIp(e.target.value)}
          required
        />
      </label>
      <label>
        Auth Result:
        <select value={result} onChange={(e) => setResult(e.target.value)}>
          <option value="success">success</option>
          <option value="failure">failure</option>
        </select>
      </label>
      <button type="submit">Submit to /score</button>
      {error && <p className="error-text">{error}</p>}
      {warning && <p className="error-text">{warning}</p>}
    </form>
  );
}
