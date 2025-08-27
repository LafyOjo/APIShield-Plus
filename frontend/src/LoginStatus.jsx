import { useEffect, useState } from "react";
import { apiFetch } from "./api";

export default function LoginStatus({ token }) {
  const [logins, setLogins] = useState({});
  const [error, setError] = useState(null);

  const load = async () => {
    try {
      const resp = await apiFetch("/api/last-logins", { skipReauth: true });
      if (!resp.ok) throw new Error(await resp.text());
      setLogins(await resp.json());
    } catch (err) {
      setError(err.message);
    }
  };

  useEffect(() => {
    if (token) {
      load();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  if (error) return <p className="error-text">{error}</p>;
  if (Object.keys(logins).length === 0) return <p>No login data.</p>;

  return (
    <div className="login-status">
      <h3>Last Logins</h3>
      <ul>
        {Object.entries(logins).map(([u, t]) => (
          <li key={u}>
            {u}: {new Date(t).toLocaleString()}
          </li>
        ))}
      </ul>
    </div>
  );
}
