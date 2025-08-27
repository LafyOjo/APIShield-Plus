/*
# App.js
# -------
# This is the main entry point for the React frontend. It wires together
# all the smaller components (forms, charts, tables, toggles) and manages
# global state like auth tokens, theme preference, and refresh triggers.
# Basically, it’s the glue between the UI pieces and the backend API.
*/

import { useState, useEffect } from "react";
import { AUTH_TOKEN_KEY, USERNAME_KEY, logAuditEvent } from "./api";
import ScoreForm from "./ScoreForm";
import AlertsTable from "./AlertsTable";
import EventsTable from "./EventsTable";
import AlertsChart from "./AlertsChart";
import SecurityToggle from "./SecurityToggle";
import LoginForm from "./LoginForm";
import AttackSim from "./AttackSim";
import UserAccounts from "./UserAccounts";
import LoginStatus from "./LoginStatus";
import "./App.css";

/*
# App component: holds top-level dashboard logic.
# Handles login vs. logout, global theme (light/dark), refreshing child tables,
# and wiring the different dashboard widgets together. Everything else
# is delegated to smaller child components to keep things modular.
*/
function App() {
  /*
  # refreshKey is a simple integer counter. When incremented,
  # it forces AlertsTable (and any other components watching it)
  # to re-render or fetch fresh data. It’s a quick, reliable way
  # to “nudge” children without complex state machinery.
  */
  const [refreshKey, setRefreshKey] = useState(0);

  /*
  # token keeps track of whether a user is logged in.
  # We read it from localStorage on startup so page reloads
  # preserve sessions. When this goes null, the UI flips back
  # to the login screen automatically.
  */
  const [token, setToken] = useState(localStorage.getItem(AUTH_TOKEN_KEY));

  /*
  # selectedUser is used by the AttackSim widget.
  # Defaulting to “alice” since that’s the demo user,
  # but you can switch accounts through the UserAccounts panel.
  # This keeps attack simulations flexible across users.
  */
  const [selectedUser, setSelectedUser] = useState("alice");

  /*
  # Theme state (dark vs light). I pull the preference from localStorage
  # so it persists across reloads. Then a side effect toggles CSS classes
  # on the root element so the whole app re-themes. The toggleTheme function
  # flips this state, and the useEffect ensures persistence and styling.
  */
  const [isDark, setIsDark] = useState(
    () => localStorage.getItem("theme") === "dark"
  );
  useEffect(() => {
    const root = document.documentElement;
    if (isDark) {
      root.classList.add("theme-dark");
      root.classList.remove("theme-light");
    } else {
      root.classList.remove("theme-dark");
      root.classList.add("theme-light");
    }
    localStorage.setItem("theme", isDark ? "dark" : "light");
  }, [isDark]);

  // Helper to flip theme state
  const toggleTheme = () => setIsDark((d) => !d);

  /*
  # Token sync: this useEffect runs every second and checks
  # localStorage for token changes (useful if multiple tabs are open).
  # If a different tab logs out or in, we pick up the change here.
  # Keeps auth state consistent across all active windows.
  */
  useEffect(() => {
    const interval = setInterval(() => {
      const current = localStorage.getItem(AUTH_TOKEN_KEY);
      setToken((prev) => (prev === current ? prev : current));
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  /*
  # Whenever token changes (login/logout), bump refreshKey.
  # This signals children like AlertsTable to pull fresh data,
  # so the dashboard doesn’t show stale alerts or events.
  # A nice clean separation of concerns—App nudges, child fetches.
  */
  useEffect(() => {
    setRefreshKey((k) => k + 1);
  }, [token]);

  /*
  # handleLogout()
  # Clears user session, logs an audit event, and resets local state.
  # Removes token + username from localStorage so reloads come up clean.
  # This ensures security by scrubbing sensitive state when logging out.
  */
  const handleLogout = async () => {
    const username = localStorage.getItem(USERNAME_KEY);
    await logAuditEvent("user_logout", username);
    localStorage.removeItem(AUTH_TOKEN_KEY);
    if (username) localStorage.removeItem(USERNAME_KEY);
    setToken(null);
  };

  /*
  # If no token: show login screen instead of the dashboard.
  # I keep it simple—just a header with a theme toggle and
  # the LoginForm component. Once LoginForm calls onLogin,
  # we’ll setToken and the main dashboard will render.
  */
  if (!token) {
    return (
      <div className="app-container stack">
        <header className="header bar">
          <h1 className="dashboard-header">APIShield+ Dashboard</h1>
          <div className="row">
            <button className="btn secondary" onClick={toggleTheme}>
              {isDark ? "Light mode" : "Dark mode"}
            </button>
          </div>
        </header>
        <section className="card">
          <h2 className="section-title">Please sign in</h2>
          <LoginForm onLogin={setToken} />
        </section>
      </div>
    );
  }

  /*
  # Main dashboard UI (when token exists).
  # This stitches together all the child widgets: accounts, status,
  # score form, alerts chart, alerts table, events table, attack sim,
  # and security toggle. Everything lives inside “card” containers
  # for consistent styling and visual separation.
  */
  return (
    <div className="app-container stack">
      <header className="header bar">
        <h1 className="dashboard-header">APIShield+ Dashboard</h1>
        <div className="row">
          <button className="btn secondary" onClick={toggleTheme}>
            {isDark ? "Light mode" : "Dark mode"}
          </button>
          <button className="btn danger" onClick={handleLogout}>
            Logout
          </button>
        </div>
      </header>

      <section className="card">
        <UserAccounts onSelect={setSelectedUser} />
      </section>

      <section className="card">
        <LoginStatus token={token} />
      </section>

      <section className="card">
        <ScoreForm token={token} onNewAlert={() => setRefreshKey((k) => k + 1)} />
      </section>

      <section className="card">
        <AlertsChart token={token} />
      </section>

      <section className="card">
        <AlertsTable refresh={refreshKey} />
      </section>

      <section className="card">
        <EventsTable />
      </section>

      <section className="card">
        <div className="attack-section">
          <AttackSim user={selectedUser} />
          <div className="security-box">
            <SecurityToggle />
          </div>
        </div>
      </section>
    </div>
  );
}

/*
# Export the App component as default.
# This is the root React component mounted by index.js,
# so the entire dashboard UI flows outward from here.
# Keeping it clean, modular, and wrapped in one default export
# makes it simple to integrate into any CRA build.
*/
export default App;
