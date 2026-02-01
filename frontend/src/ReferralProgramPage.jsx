import { useEffect, useState } from "react";
import { apiFetch } from "./api";

export default function ReferralProgramPage() {
  const [config, setConfig] = useState(null);
  const [summary, setSummary] = useState(null);
  const [invites, setInvites] = useState([]);
  const [redemptions, setRedemptions] = useState([]);
  const [newInvite, setNewInvite] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);

  const loadAll = async () => {
    setLoading(true);
    setError(null);
    try {
      const [cfgResp, summaryResp, invitesResp, redemptionsResp] = await Promise.all([
        apiFetch("/referrals/config"),
        apiFetch("/referrals/summary"),
        apiFetch("/referrals/invites"),
        apiFetch("/referrals/redemptions"),
      ]);
      if (cfgResp.ok) setConfig(await cfgResp.json());
      if (summaryResp.ok) setSummary(await summaryResp.json());
      if (invitesResp.ok) setInvites(await invitesResp.json());
      if (redemptionsResp.ok) setRedemptions(await redemptionsResp.json());
    } catch (err) {
      setError(err.message || "Failed to load referrals");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAll();
  }, []);

  const handleCreateInvite = async () => {
    setCreating(true);
    setError(null);
    setNewInvite(null);
    try {
      const resp = await apiFetch("/referrals/invites", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (!resp.ok) {
        throw new Error(await resp.text());
      }
      const data = await resp.json();
      setNewInvite(data.invite);
      await loadAll();
    } catch (err) {
      setError(err.message || "Unable to create invite");
    } finally {
      setCreating(false);
    }
  };

  const handleCopy = async (value) => {
    try {
      await navigator.clipboard.writeText(value);
    } catch (err) {
      console.error("Clipboard copy failed", err);
    }
  };

  if (loading) {
    return (
      <section className="card">
        <h2>Referral Program</h2>
        <p>Loading...</p>
      </section>
    );
  }

  return (
    <div className="stack">
      <section className="card">
        <h2>Referral Program</h2>
        <p className="subtle">
          Invite peers and earn rewards once they become paying customers.
        </p>
        {config && !config.is_enabled && (
          <p style={{ color: "var(--warning)" }}>
            Referrals are currently disabled. Contact support to enable.
          </p>
        )}
        {summary && (
          <div className="grid" style={{ gap: "1rem", marginTop: "1rem" }}>
            <div className="card">
              <h4>Credit balance</h4>
              <p>£{summary.credit_balance.toFixed(2)}</p>
            </div>
            <div className="card">
              <h4>Pending rewards</h4>
              <p>{summary.pending_redemptions}</p>
            </div>
            <div className="card">
              <h4>Applied rewards</h4>
              <p>{summary.applied_redemptions}</p>
            </div>
          </div>
        )}
        {config && (
          <p style={{ marginTop: "1rem" }}>
            Reward: {config.reward_type.replace("_", " ")} ({config.reward_value})
          </p>
        )}
        <button className="btn" onClick={handleCreateInvite} disabled={creating || !config?.is_enabled}>
          {creating ? "Creating..." : "Create invite link"}
        </button>
        {newInvite?.share_url && (
          <div className="card" style={{ marginTop: "1rem" }}>
            <h4>New invite</h4>
            <p className="mono">{newInvite.share_url}</p>
            <button className="btn secondary" onClick={() => handleCopy(newInvite.share_url)}>
              Copy link
            </button>
          </div>
        )}
        {error && <p style={{ color: "var(--danger)" }}>{error}</p>}
      </section>

      <section className="card">
        <h3>Active invite links</h3>
        {invites.length === 0 ? (
          <p className="subtle">No invites yet.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Code</th>
                <th>Uses</th>
                <th>Status</th>
                <th>Expires</th>
                <th>Share</th>
              </tr>
            </thead>
            <tbody>
              {invites.map((invite) => (
                <tr key={invite.id}>
                  <td className="mono">{invite.code}</td>
                  <td>{invite.uses_count}/{invite.max_uses}</td>
                  <td>{invite.status}</td>
                  <td>{invite.expires_at ? new Date(invite.expires_at).toLocaleDateString() : "-"}</td>
                  <td>
                    {invite.share_url && (
                      <button className="btn secondary" onClick={() => handleCopy(invite.share_url)}>
                        Copy
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="card">
        <h3>Redemptions</h3>
        {redemptions.length === 0 ? (
          <p className="subtle">No redemptions yet.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Invite</th>
                <th>Tenant</th>
                <th>Status</th>
                <th>Redeemed</th>
                <th>Reward</th>
              </tr>
            </thead>
            <tbody>
              {redemptions.map((redemption) => (
                <tr key={redemption.id}>
                  <td className="mono">{redemption.invite_id}</td>
                  <td>{redemption.new_tenant_id}</td>
                  <td>{redemption.status}</td>
                  <td>{new Date(redemption.redeemed_at).toLocaleDateString()}</td>
                  <td>{redemption.reward_applied_at ? "Applied" : "Pending"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
