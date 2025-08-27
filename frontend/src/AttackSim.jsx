import React, { useState, useEffect } from "react";
import { USER_DATA } from "./UserAccounts";
import { apiFetch } from "./api";

const SHOP_URL = process.env.REACT_APP_SHOP_URL || "http://localhost:3005";

const DUMMY_PASSWORDS = ["wrongpass", "123456", "password1", "secret", "letmein"];

async function recordStuffingAttempt({ user, success }) {
  try {
    await apiFetch("/events/auth", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user,
        action: "stuffing_attempt",
        success,
        source: "apishield+",
      }),
      skipReauth: true,
    });
  } catch (err) {
    console.error("Record attempt error", err);
  }
}

export default function AttackSim({ user }) {
  const [targetUser, setTargetUser] = useState(user || "alice");
  const [attemptsInput, setAttemptsInput] = useState(20);
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);
  const [chainToken, setChainToken] = useState(null);
  const [blockedBanner, setBlockedBanner] = useState(false);
  const [demoBlocks, setDemoBlocks] = useState(true); // omit chain sometimes to demo blocking

  useEffect(() => {
    if (user) setTargetUser(user);
  }, [user]);

  useEffect(() => {
    async function ensureUsers() {
      for (const [name, info] of Object.entries(USER_DATA)) {
        try {
          // backend register
          await apiFetch("/register", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username: name, password: info.password }),
            skipReauth: true,
          });
          // demo shop register + seed cart
          await fetch(`${SHOP_URL}/register`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username: name, password: info.password }),
          });
          await fetch(`${SHOP_URL}/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username: name, password: info.password }),
            credentials: "include",
          });
          await fetch(`${SHOP_URL}/cart`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ productId: 1 }),
            credentials: "include",
          });
        } catch {
          // likely already registered; ignore
        }
      }
    }
    ensureUsers();
  }, []);

  const fetchChainToken = async () => {
    try {
      const resp = await apiFetch("/api/security/chain", { skipReauth: true });
      if (resp.status === 401) {
        setError("Unauthorized to fetch chain token");
        return null;
      }
      if (resp.ok) {
        const data = await resp.json();
        setChainToken(data.chain);
        return data.chain;
      }
    } catch (err) {
      console.error("Chain fetch error", err);
    }
    return null;
  };

  const simulateAttack = async () => {
    setRunning(true);
    setResults(null);
    setError(null);
    setBlockedBanner(false);
    setChainToken(null);

    let securityEnabled = false;
    let currentChain = null;

    try {
      const secResp = await apiFetch("/api/security", { skipReauth: true });
      if (secResp.status === 401) {
        setError("Unauthorized to check security state");
        setRunning(false);
        return;
      }
      if (secResp.ok) {
        const data = await secResp.json();
        securityEnabled = data.enabled;
        if (securityEnabled) currentChain = await fetchChainToken();
      }
    } catch (err) {
      console.error("Security state error", err);
    }

    let successes = 0;
    let blocked = 0;
    let firstAttempt = null;
    let firstTime = null;
    let firstInfo = null;
    let firstCart = null;

    const start = performance.now();

    for (let i = 0; i < attemptsInput; i++) {
      const pwd = DUMMY_PASSWORDS[i % DUMMY_PASSWORDS.length];

      // try login against backend
      let loginOk = false;
      let token = null;
      try {
        const resp = await apiFetch(`/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username: targetUser, password: pwd }),
          skipReauth: true,
        });
        loginOk = resp.ok;
        if (loginOk) {
          const data = await resp.json();
          token = data.access_token;
        }
      } catch (err) {
        console.error("Login error", err);
      }

      // record attempt
      recordStuffingAttempt({ user: targetUser, success: loginOk }).catch(() => {});

      // try demo shop login
      let shopOk = false;
      try {
        const shopResp = await fetch(`${SHOP_URL}/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username: targetUser, password: pwd }),
          credentials: "include",
        });
        shopOk = shopResp.status === 200;
      } catch (err) {
        console.error("Shop login error", err);
      }

      // score the attempt
      try {
        const headers = { "Content-Type": "application/json" };
        // omit the chain every 3rd attempt when demoBlocks is on so we can see blocks
        const shouldSendChain = !(demoBlocks && (i % 3 === 2));
        if (securityEnabled && currentChain && shouldSendChain) {
          headers["X-Chain-Password"] = currentChain;
        }

        const scoreResp = await apiFetch("/score", {
          method: "POST",
          headers,
          body: JSON.stringify({
            client_ip: "10.0.0.1",
            auth_result: loginOk ? "success" : "failure",
          }),
          skipReauth: true,
        });

        if (scoreResp.status === 401) {
          // blocked by Zero-Trust / ReAuth
          blocked++;
          setBlockedBanner(true);
        } else if (scoreResp.ok) {
          const data = await scoreResp.json();
          if (data.status === "blocked") {
            blocked++;
            setBlockedBanner(true);
          }
        }
      } catch (err) {
        console.error("Score error", err);
      }

      if (securityEnabled) {
        currentChain = await fetchChainToken();
      }

      if (loginOk) {
        if (firstAttempt === null) {
          firstAttempt = i + 1;
          firstTime = (performance.now() - start) / 1000;
          if (token) {
            try {
              const infoResp = await apiFetch("/api/me", {
                headers: { Authorization: `Bearer ${token}` },
                skipReauth: true,
              });
              if (infoResp.ok) firstInfo = await infoResp.json();
            } catch (err) {
              console.error("Info error", err);
            }
          }
        }
      }

      if (shopOk && firstCart === null) {
        try {
          const cartResp = await fetch(`${SHOP_URL}/cart`, { credentials: "include" });
          if (cartResp.ok) firstCart = await cartResp.json();
        } catch (err) {
          console.error("Fetch shop info", err);
        }
      }

      setResults({
        attempts: i + 1,
        successes,
        blocked,
        first_success_attempt: firstAttempt,
        first_success_time: firstTime,
        first_user_info: firstInfo,
        first_cart: firstCart,
      });

      await new Promise((res) => setTimeout(res, 100));
    }

    const totalTime = (performance.now() - start) / 1000;
    setResults((r) => ({ ...r, total_time: totalTime }));
    setRunning(false);
  };

  return (
    <div className="attack-sim">
      <h2>Credential Stuffing Simulation</h2>

      {blockedBanner && (
        <p className="error-text" style={{ color: "var(--danger,#d33)" }}>
          Attack blocked by security
        </p>
      )}

      <div className="attack-controls">
        <label>
          Target User:
          <select value={targetUser} onChange={(e) => setTargetUser(e.target.value)}>
            <option value="alice">Alice</option>
            <option value="ben">Ben</option>
          </select>
        </label>

        <label>
          Attempts:
          <input
            type="number"
            min="1"
            value={attemptsInput}
            onChange={(e) => setAttemptsInput(parseInt(e.target.value, 10))}
          />
        </label>

        <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input
            type="checkbox"
            checked={demoBlocks}
            onChange={(e) => setDemoBlocks(e.target.checked)}
          />
          Demo blocks (omit chain every 3rd try)
        </label>

        <button onClick={simulateAttack} disabled={running}>
          {running ? "Running..." : "Start Attack"}
        </button>
      </div>

      {error && <p className="error-text">{error}</p>}

      {results && (
        <div className="attack-results">
          <p>Total Attempts: {results.attempts}</p>
          <p>Successful Logins: {results.successes}</p>
          <p>Blocked by Security: {results.blocked}</p>

          {results.first_success_attempt && (
            <>
              <p>
                First Success: attempt {results.first_success_attempt} (in{" "}
                {results.first_success_time?.toFixed(2)}s)
              </p>
              {results.first_user_info && (
                <p>
                  User Info <code>{JSON.stringify(results.first_user_info)}</code>
                </p>
              )}
              {results.first_cart && (
                <>
                  <h4>Stolen Cart Items</h4>
                  <pre>{JSON.stringify(results.first_cart, null, 2)}</pre>
                </>
              )}
            </>
          )}

          {results.total_time && (
            <p>Total Time: {results.total_time.toFixed(2)}s</p>
          )}
        </div>
      )}
    </div>
  );
}
