import { useEffect, useState } from "react";
import { apiFetch } from "./api";

export default function EventsTable() {
  const [events, setEvents] = useState([]);
  const [error, setError] = useState(null);
  const [hours, setHours] = useState(24);

  const load = async () => {
    const query = hours ? `?hours=${hours}` : "";
    try {
      const resp = await apiFetch(`/api/events${query}`, { skipReauth: true });
      if (!resp.ok) throw new Error(await resp.text());
      setEvents(await resp.json());
    } catch (err) {
      setError(err.message);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hours]);

  if (error) return <p className="error-text">{error}</p>;
  if (events.length === 0) return <p>No events.</p>;

  return (
    <div>
      <div className="toggle-buttons">
        <button onClick={() => setHours(null)} className={hours === null ? "active" : ""}>All</button>
        <button onClick={() => setHours(1)} className={hours === 1 ? "active" : ""}>1h</button>
        <button onClick={() => setHours(24)} className={hours === 24 ? "active" : ""}>24h</button>
      </div>
      <div style={{ overflowX: "auto" }}>
        <table className="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>User</th>
              <th>Action</th>
              <th>Success</th>
              <th>Timestamp</th>
            </tr>
          </thead>
          <tbody>
            {events.map((e) => (
              <tr key={e.id}>
                <td>{e.id}</td>
                <td>{e.username}</td>
                <td>{e.action}</td>
                <td>{e.success ? "yes" : "no"}</td>
                <td>{new Date(e.timestamp).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
