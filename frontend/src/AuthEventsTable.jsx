import { useEffect, useState } from "react";
import { apiFetch } from "./api";

export default function AuthEventsTable({ refresh, limit = 50, tableClassName = "table" }) {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const resp = await apiFetch(`/events/auth?limit=${limit}`, { skipReauth: true });
      if (!resp.ok) throw new Error(await resp.text());
      setEvents(await resp.json());
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refresh, limit]);

  return (
    <div>
      <button onClick={load}>Refresh</button>
      {error ? (
        <p className="error-text">{error}</p>
      ) : loading ? (
        <p>Loading…</p>
      ) : events.length === 0 ? (
        <p>No events yet.</p>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table className={tableClassName}>
            <thead>
              <tr>
                <th>ID</th>
                <th>User</th>
                <th>Action</th>
                <th>Success</th>
                <th>Source</th>
                <th>Timestamp</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e) => (
                <tr key={e.id}>
                  <td>{e.id}</td>
                  <td>{e.user ?? ""}</td>
                  <td>{e.action}</td>
                  <td>
                    {e.success ? (
                      <span className="badge success">yes</span>
                    ) : (
                      <span className="badge danger">no</span>
                    )}
                  </td>
                  <td>{e.source}</td>
                  <td>
                    {new Date(e.created_at).toLocaleString("en-GB", { hour12: false })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

