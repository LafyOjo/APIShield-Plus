import { useEffect, useState } from "react";
import { apiFetch } from "./api";

const EMPTY_CREATE = {
  name: "",
  code: "",
  commission_type: "percent",
  commission_value: 10,
};

export default function AdminAffiliatePage() {
  const [partners, setPartners] = useState([]);
  const [selectedPartner, setSelectedPartner] = useState(null);
  const [attributions, setAttributions] = useState([]);
  const [ledger, setLedger] = useState([]);
  const [summary, setSummary] = useState(null);
  const [form, setForm] = useState(EMPTY_CREATE);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const loadPartners = async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await apiFetch("/api/v1/admin/affiliates/partners");
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      setPartners(data || []);
    } catch (err) {
      setError(err.message || "Failed to load partners");
    } finally {
      setLoading(false);
    }
  };

  const loadPartnerDetail = async (partner) => {
    if (!partner) return;
    setSelectedPartner(partner);
    setError(null);
    try {
      const [attrResp, ledgerResp, summaryResp] = await Promise.all([
        apiFetch(`/api/v1/admin/affiliates/partners/${partner.id}/attributions`),
        apiFetch(`/api/v1/admin/affiliates/partners/${partner.id}/ledger`),
        apiFetch(`/api/v1/admin/affiliates/partners/${partner.id}/summary`),
      ]);
      setAttributions(attrResp.ok ? await attrResp.json() : []);
      setLedger(ledgerResp.ok ? await ledgerResp.json() : []);
      setSummary(summaryResp.ok ? await summaryResp.json() : null);
    } catch (err) {
      setError(err.message || "Failed to load partner detail");
    }
  };

  useEffect(() => {
    loadPartners();
  }, []);

  const handleCreate = async () => {
    setError(null);
    try {
      const payload = {
        name: form.name,
        code: form.code || undefined,
        commission_type: form.commission_type,
        commission_value: Number(form.commission_value),
      };
      const resp = await apiFetch("/api/v1/admin/affiliates/partners", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!resp.ok) throw new Error(await resp.text());
      setForm(EMPTY_CREATE);
      await loadPartners();
    } catch (err) {
      setError(err.message || "Failed to create partner");
    }
  };

  return (
    <section className="card">
      <h2 className="section-title">Affiliate Program</h2>
      <p className="muted">Manage partners, attributions, and commissions.</p>
      {error && <p className="error">{error}</p>}
      {loading && <p className="muted">Loading...</p>}

      <div className="admin-grid" style={{ marginTop: "1rem" }}>
        <div className="admin-list">
          <h3>Partners</h3>
          <ul className="list">
            {partners.map((partner) => (
              <li key={partner.id}>
                <button
                  className={`btn tertiary ${selectedPartner?.id === partner.id ? "active" : ""}`}
                  onClick={() => loadPartnerDetail(partner)}
                >
                  <div>
                    <strong>{partner.name}</strong>
                    <div className="muted small">{partner.code} · {partner.status}</div>
                  </div>
                </button>
              </li>
            ))}
          </ul>

          <div className="card" style={{ marginTop: "1rem" }}>
            <h4>Create partner</h4>
            <div className="field">
              <label className="label">Name</label>
              <input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </div>
            <div className="field">
              <label className="label">Code (optional)</label>
              <input className="input" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} />
            </div>
            <div className="field">
              <label className="label">Commission type</label>
              <select className="input" value={form.commission_type} onChange={(e) => setForm({ ...form, commission_type: e.target.value })}>
                <option value="percent">Percent</option>
                <option value="flat">Flat</option>
              </select>
            </div>
            <div className="field">
              <label className="label">Commission value</label>
              <input className="input" type="number" value={form.commission_value} onChange={(e) => setForm({ ...form, commission_value: e.target.value })} />
            </div>
            <button className="btn" onClick={handleCreate}>Create</button>
          </div>
        </div>

        <div className="admin-detail">
          {!selectedPartner ? (
            <p className="muted">Select a partner to view details.</p>
          ) : (
            <>
              <h3>{selectedPartner.name}</h3>
              <p className="muted">Code: {selectedPartner.code}</p>
              {summary && (
                <div className="grid" style={{ gap: "1rem" }}>
                  <div className="card"><h4>Signups</h4><p>{summary.signups}</p></div>
                  <div className="card"><h4>Conversions</h4><p>{summary.conversions}</p></div>
                  <div className="card"><h4>Pending</h4><p>£{summary.commission_pending.toFixed(2)}</p></div>
                  <div className="card"><h4>Paid</h4><p>£{summary.commission_paid.toFixed(2)}</p></div>
                </div>
              )}

              <div className="admin-section">
                <h4>Attributions</h4>
                {attributions.length === 0 ? (
                  <p className="muted">No attributions yet.</p>
                ) : (
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Tenant</th>
                        <th>First touch</th>
                        <th>Last touch</th>
                      </tr>
                    </thead>
                    <tbody>
                      {attributions.map((row) => (
                        <tr key={row.id}>
                          <td>{row.tenant_id}</td>
                          <td>{new Date(row.first_touch_at).toLocaleString()}</td>
                          <td>{new Date(row.last_touch_at).toLocaleString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>

              <div className="admin-section">
                <h4>Commission ledger</h4>
                {ledger.length === 0 ? (
                  <p className="muted">No commissions yet.</p>
                ) : (
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Tenant</th>
                        <th>Amount</th>
                        <th>Status</th>
                        <th>Earned</th>
                        <th>Paid</th>
                      </tr>
                    </thead>
                    <tbody>
                      {ledger.map((row) => (
                        <tr key={row.id}>
                          <td>{row.tenant_id}</td>
                          <td>£{Number(row.amount).toFixed(2)}</td>
                          <td>{row.status}</td>
                          <td>{row.earned_at ? new Date(row.earned_at).toLocaleDateString() : "-"}</td>
                          <td>{row.paid_at ? new Date(row.paid_at).toLocaleDateString() : "-"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
