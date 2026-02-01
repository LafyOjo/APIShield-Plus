import { useEffect, useState } from "react";
import { apiFetch } from "./api";

const EMPTY_FORM = {
  status: "draft",
  safety_notes: "",
  tags: "",
};

export default function AdminMarketplacePage() {
  const [templates, setTemplates] = useState([]);
  const [selected, setSelected] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const loadTemplates = async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await apiFetch("/api/v1/admin/marketplace/templates");
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      setTemplates(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err.message || "Unable to load templates");
    } finally {
      setLoading(false);
    }
  };

  const selectTemplate = (template) => {
    setSelected(template);
    setForm({
      status: template.status || "draft",
      safety_notes: template.safety_notes || "",
      tags: (template.tags || []).join(", "),
    });
  };

  useEffect(() => {
    loadTemplates();
  }, []);

  const handleUpdate = async () => {
    if (!selected) return;
    setError(null);
    try {
      const payload = {
        status: form.status,
        safety_notes: form.safety_notes || null,
        tags: form.tags
          ? form.tags.split(",").map((tag) => tag.trim()).filter(Boolean)
          : [],
      };
      const resp = await apiFetch(`/api/v1/admin/marketplace/templates/${selected.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!resp.ok) throw new Error(await resp.text());
      const updated = await resp.json();
      setTemplates((prev) =>
        prev.map((item) => (item.id === updated.id ? updated : item))
      );
      setSelected(updated);
    } catch (err) {
      setError(err.message || "Update failed");
    }
  };

  return (
    <section className="card">
      <h2 className="section-title">Marketplace Moderation</h2>
      <p className="muted">Approve or reject community templates.</p>
      {error && <p className="error">{error}</p>}
      {loading && <p className="muted">Loading...</p>}

      <div className="admin-grid" style={{ marginTop: "1rem" }}>
        <div className="admin-list">
          <h3>Templates</h3>
          <ul className="list">
            {templates.map((item) => (
              <li key={item.id}>
                <button
                  className={`btn tertiary ${selected?.id === item.id ? "active" : ""}`}
                  onClick={() => selectTemplate(item)}
                >
                  <div>
                    <strong>{item.title}</strong>
                    <div className="muted small">{item.template_type} · {item.status}</div>
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </div>

        <div className="admin-detail">
          {!selected ? (
            <p className="muted">Select a template to review.</p>
          ) : (
            <>
              <h3>{selected.title}</h3>
              <p className="muted">{selected.description}</p>
              <div className="field">
                <label className="label">Status</label>
                <select
                  className="input"
                  value={form.status}
                  onChange={(event) => setForm({ ...form, status: event.target.value })}
                >
                  <option value="draft">Draft</option>
                  <option value="published">Published</option>
                  <option value="rejected">Rejected</option>
                </select>
              </div>
              <div className="field">
                <label className="label">Tags</label>
                <input
                  className="input"
                  value={form.tags}
                  onChange={(event) => setForm({ ...form, tags: event.target.value })}
                />
              </div>
              <div className="field">
                <label className="label">Safety notes</label>
                <textarea
                  className="textarea"
                  rows={4}
                  value={form.safety_notes}
                  onChange={(event) => setForm({ ...form, safety_notes: event.target.value })}
                />
              </div>
              <button className="btn" onClick={handleUpdate}>Save changes</button>

              <div className="admin-section">
                <h4>Content preview</h4>
                <pre className="code-block">{JSON.stringify(selected.content_json, null, 2)}</pre>
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
