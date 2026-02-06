/*
# App.js
# -------
# This is the main entry point for the React frontend. It wires together
# all the smaller components (forms, charts, tables, toggles) and manages
# global state like auth tokens, theme preference, and refresh triggers.
# Basically, it’s the glue between the UI pieces and the backend API.
*/

import { useState, useEffect, useRef } from "react";
import { ACTIVE_TENANT_KEY, AUTH_TOKEN_KEY, USERNAME_KEY, apiFetch, logAuditEvent } from "./api";
import { captureNavigationTimings, markDashboardReady } from "./perf";
import ScoreForm from "./ScoreForm";
import AlertsTable from "./AlertsTable";
import EventsTable from "./EventsTable";
import AlertsChart from "./AlertsChart";
import SecurityToggle from "./SecurityToggle";
import LoginForm from "./LoginForm";
import AttackSim from "./AttackSim";
import UserAccounts from "./UserAccounts";
import LoginStatus from "./LoginStatus";
import SecurityMapPage from "./SecurityMapPage";
import SecurityEventsPage from "./SecurityEventsPage";
import RevenueIntegrityIncidentsPage from "./RevenueIntegrityIncidentsPage";
import RevenueIntegrityIncidentDetailPage from "./RevenueIntegrityIncidentDetailPage";
import RemediationWorkspacePage from "./RemediationWorkspacePage";
import RevenueLeakHeatmapPage from "./RevenueLeakHeatmapPage";
import WebsiteSettingsPage from "./WebsiteSettingsPage";
import OnboardingWizardPage from "./OnboardingWizardPage";
import NotificationsSettingsPage from "./NotificationsSettingsPage";
import BrandingSettingsPage from "./BrandingSettingsPage";
import BillingPage from "./BillingPage";
import ReferralProgramPage from "./ReferralProgramPage";
import PortfolioPage from "./PortfolioPage";
import ComplianceAuditPage from "./ComplianceAuditPage";
import ComplianceRetentionPage from "./ComplianceRetentionPage";
import AdminConsolePage from "./AdminConsolePage";
import AdminStatusPage from "./AdminStatusPage";
import AdminActivationPage from "./AdminActivationPage";
import AdminAffiliatePage from "./AdminAffiliatePage";
import AdminGrowthPage from "./AdminGrowthPage";
import StatusPage from "./StatusPage";
import DocsHubPage from "./DocsHubPage";
import IntegrationsDirectoryPage, { PublicIntegrationsPage } from "./IntegrationsDirectoryPage";
import MarketplacePage, { PublicMarketplacePage } from "./MarketplacePage";
import MarketplaceTemplateDetailPage, { PublicMarketplaceTemplateDetailPage } from "./MarketplaceTemplateDetailPage";
import AdminMarketplacePage from "./AdminMarketplacePage";
import PartnerDashboardPage from "./PartnerDashboardPage";
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
  const [currentRoute, setCurrentRoute] = useState(window.location.pathname);
  const perfDashboardMarked = useRef(false);

  /*
  # token keeps track of whether a user is logged in.
  # We read it from localStorage on startup so page reloads
  # preserve sessions. When this goes null, the UI flips back
  # to the login screen automatically.
  */
  const [token, setToken] = useState(localStorage.getItem(AUTH_TOKEN_KEY));
  const [partnerProfile, setPartnerProfile] = useState(null);
  const [partnerChecked, setPartnerChecked] = useState(false);
  const [activeTenantId, setActiveTenantId] = useState(
    localStorage.getItem(ACTIVE_TENANT_KEY) || ""
  );
  const [branding, setBranding] = useState(null);

  useEffect(() => {
    const hashParams = new URLSearchParams(
      window.location.hash ? window.location.hash.slice(1) : ""
    );
    const tokenParam = hashParams.get("sso_token");
    if (!tokenParam) {
      return;
    }
    const userParam = hashParams.get("sso_user");
    const tenantParam = hashParams.get("tenant");
    localStorage.setItem(AUTH_TOKEN_KEY, tokenParam);
    if (userParam) localStorage.setItem(USERNAME_KEY, userParam);
    if (tenantParam) localStorage.setItem(ACTIVE_TENANT_KEY, tenantParam);
    setToken(tokenParam);
    const cleanPath = window.location.pathname === "/sso/callback"
      ? "/"
      : window.location.pathname;
    window.history.replaceState({}, "", cleanPath);
  }, []);

  useEffect(() => {
    captureNavigationTimings();
  }, []);

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

  useEffect(() => {
    const interval = setInterval(() => {
      const current = localStorage.getItem(ACTIVE_TENANT_KEY) || "";
      setActiveTenantId((prev) => (prev === current ? prev : current));
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const handlePop = () => setCurrentRoute(window.location.pathname);
    window.addEventListener("popstate", handlePop);
    return () => window.removeEventListener("popstate", handlePop);
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

  useEffect(() => {
    if (!token || perfDashboardMarked.current) return;
    requestAnimationFrame(() => {
      markDashboardReady({ route: currentRoute || "/" });
      perfDashboardMarked.current = true;
    });
  }, [token, currentRoute]);

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

  const navigate = (path) => {
    if (window.location.pathname === path) return;
    window.history.pushState({}, "", path);
    setCurrentRoute(path);
  };

  useEffect(() => {
    let active = true;
    if (!token) {
      setPartnerProfile(null);
      setPartnerChecked(false);
      return () => {
        active = false;
      };
    }
    const loadPartnerProfile = async () => {
      try {
        const resp = await apiFetch("/api/v1/partners/me", { skipReauth: true });
        if (!active) return;
        if (resp.ok) {
          const data = await resp.json();
          setPartnerProfile(data);
        } else {
          setPartnerProfile(null);
        }
      } catch (err) {
        if (active) setPartnerProfile(null);
      } finally {
        if (active) setPartnerChecked(true);
      }
    };
    loadPartnerProfile();
    return () => {
      active = false;
    };
  }, [token]);

  useEffect(() => {
    let active = true;
    if (!token || partnerProfile) {
      setBranding(null);
      return () => {
        active = false;
      };
    }
    if (!activeTenantId) {
      setBranding(null);
      return () => {
        active = false;
      };
    }
    const loadBranding = async () => {
      try {
        const resp = await apiFetch("/api/v1/branding", { skipReauth: true });
        if (!active) return;
        if (!resp.ok) {
          setBranding(null);
          return;
        }
        const data = await resp.json();
        if (active) setBranding(data);
      } catch (err) {
        if (active) setBranding(null);
      }
    };
    loadBranding();
    return () => {
      active = false;
    };
  }, [token, partnerProfile, activeTenantId]);

  useEffect(() => {
    const root = document.documentElement;
    const applyColor = (name, value) => {
      if (value) {
        root.style.setProperty(name, value);
      } else {
        root.style.removeProperty(name);
      }
    };
    const pickContrast = (hex) => {
      if (!hex || !hex.startsWith("#") || hex.length !== 7) return null;
      const r = parseInt(hex.slice(1, 3), 16);
      const g = parseInt(hex.slice(3, 5), 16);
      const b = parseInt(hex.slice(5, 7), 16);
      const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
      return luminance > 0.6 ? "#0b1220" : "#ffffff";
    };
    if (branding && branding.is_enabled) {
      const accent = branding.primary_color || branding.accent_color;
      applyColor("--accent", accent);
      applyColor("--accent-contrast", pickContrast(accent));
    } else {
      applyColor("--accent", null);
      applyColor("--accent-contrast", null);
    }
    if (branding && branding.is_enabled && branding.brand_name) {
      document.title = `${branding.brand_name} Dashboard`;
    } else {
      document.title = "APIShield+ Dashboard";
    }
  }, [branding]);

  useEffect(() => {
    if (partnerProfile && !currentRoute.startsWith("/partner")) {
      navigate("/partner");
    }
  }, [partnerProfile, currentRoute]);

  const isMapRoute =
    currentRoute.startsWith("/dashboard/security/map") ||
    currentRoute.startsWith("/map") ||
    currentRoute.startsWith("/dashboard/map");
  const isEventsRoute =
    currentRoute.startsWith("/dashboard/security/events") ||
    currentRoute.startsWith("/security/events");
  const isNotificationsRoute = currentRoute.startsWith("/dashboard/settings/notifications");
  const isBrandingRoute = currentRoute.startsWith("/dashboard/settings/branding");
  const isBillingRoute = currentRoute.startsWith("/billing");
  const isComplianceRoute =
    currentRoute.startsWith("/dashboard/compliance/audit") ||
    currentRoute.startsWith("/compliance/audit") ||
    currentRoute.startsWith("/dashboard/compliance/retention") ||
    currentRoute.startsWith("/compliance/retention");
  const isReferralsRoute =
    currentRoute.startsWith("/dashboard/referrals") ||
    currentRoute.startsWith("/referrals");
  const isPortfolioRoute = currentRoute.startsWith("/dashboard/portfolio");
  const websiteSettingsMatch = currentRoute.match(
    /^\/dashboard\/websites\/(\d+)\/settings/
  );
  const isWebsiteSettingsRoute = currentRoute.startsWith("/dashboard/websites");
  const websiteSettingsId = websiteSettingsMatch ? websiteSettingsMatch[1] : null;
  const isComplianceRetentionRoute =
    currentRoute.startsWith("/dashboard/compliance/retention") ||
    currentRoute.startsWith("/compliance/retention");
  const isOnboardingRoute =
    currentRoute.startsWith("/dashboard/onboarding") ||
    currentRoute.startsWith("/onboarding");
  const isPartnerRoute = currentRoute.startsWith("/partner");
  const isAdminRoute =
    currentRoute.startsWith("/admin");
  const isAdminStatusRoute = currentRoute.startsWith("/admin/status");
  const isAdminActivationRoute = currentRoute.startsWith("/admin/activation");
  const isAdminAffiliateRoute = currentRoute.startsWith("/admin/affiliates");
  const isAdminGrowthRoute = currentRoute.startsWith("/admin/growth");
  const isAdminMarketplaceRoute = currentRoute.startsWith("/admin/marketplace");
  const isStatusRoute = currentRoute.startsWith("/status");
  const isHelpRoute =
    currentRoute.startsWith("/dashboard/help") ||
    currentRoute.startsWith("/help");
  const isIntegrationsRoute =
    currentRoute.startsWith("/dashboard/integrations") ||
    currentRoute.startsWith("/integrations");
  const marketplaceDetailMatch = currentRoute.match(
    /^\/dashboard\/marketplace\/(\d+)/
  );
  const marketplacePublicDetailMatch = currentRoute.match(/^\/marketplace\/(\d+)/);
  const marketplaceId = marketplaceDetailMatch ? marketplaceDetailMatch[1] : null;
  const marketplacePublicId = marketplacePublicDetailMatch ? marketplacePublicDetailMatch[1] : null;
  const isMarketplaceRoute =
    currentRoute.startsWith("/dashboard/marketplace") ||
    currentRoute.startsWith("/marketplace");
  const revenuePrefix = "/dashboard/revenue-integrity";
  const leaksPrefix = "/dashboard/revenue-integrity/leaks";
  const incidentDetailMatch = currentRoute.match(
    /^\/dashboard\/revenue-integrity\/incidents\/(\d+)/
  );
  const remediationMatch = currentRoute.match(/^\/dashboard\/remediation\/(\d+)/);
  const isRevenueRoute = currentRoute.startsWith(revenuePrefix);
  const isIncidentDetailRoute = Boolean(incidentDetailMatch);
  const incidentId = incidentDetailMatch ? incidentDetailMatch[1] : null;
  const isRemediationRoute = Boolean(remediationMatch);
  const remediationIncidentId = remediationMatch ? remediationMatch[1] : null;
  const isLeaksRoute = currentRoute.startsWith(leaksPrefix);

  /*
  # If no token: show login screen instead of the dashboard.
  # I keep it simple—just a header with a theme toggle and
  # the LoginForm component. Once LoginForm calls onLogin,
  # we’ll setToken and the main dashboard will render.
  */
  if (isStatusRoute) {
    return <StatusPage />;
  }

  if (!token && isIntegrationsRoute) {
    return <PublicIntegrationsPage />;
  }

  if (!token && isMarketplaceRoute) {
    if (marketplacePublicId) {
      return <PublicMarketplaceTemplateDetailPage templateId={marketplacePublicId} />;
    }
    return <PublicMarketplacePage />;
  }

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

  const brandTitle =
    branding && branding.is_enabled && branding.brand_name ? branding.brand_name : "APIShield+";
  const brandLogo = branding && branding.is_enabled ? branding.logo_url : null;

  if (isPartnerRoute) {
    return (
      <div className="app-container stack">
        <header className="header bar">
          <div>
            <h1 className="dashboard-header">APIShield+ Partner Portal</h1>
            {partnerProfile && (
              <div className="muted small">
                {partnerProfile.partner_name} · {partnerProfile.partner_code}
              </div>
            )}
          </div>
          <div className="row">
            <button className="btn secondary" onClick={toggleTheme}>
              {isDark ? "Light mode" : "Dark mode"}
            </button>
            <button className="btn danger" onClick={handleLogout}>
              Logout
            </button>
          </div>
        </header>
        <PartnerDashboardPage
          partnerProfile={partnerProfile}
          partnerChecked={partnerChecked}
        />
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
        <div className="brand-header">
          {brandLogo && (
            <img
              src={brandLogo}
              alt={`${brandTitle} logo`}
              className="brand-logo"
            />
          )}
          <h1 className="dashboard-header">{brandTitle} Dashboard</h1>
        </div>
        <div className="row">
          <button
            className={`btn secondary nav-tab ${
              !isMapRoute && !isEventsRoute && !isRevenueRoute && !isNotificationsRoute
                && !isBillingRoute && !isComplianceRoute && !isAdminRoute && !isWebsiteSettingsRoute
                && !isOnboardingRoute && !isHelpRoute && !isMarketplaceRoute && !isBrandingRoute
                && !isPortfolioRoute
                ? "active"
                : ""
            }`}
            onClick={() => navigate("/")}
          >
            Overview
          </button>
          <button
            className={`btn secondary nav-tab ${isMapRoute ? "active" : ""}`}
            onClick={() => navigate("/dashboard/security/map")}
          >
            Security Map
          </button>
          <button
            className={`btn secondary nav-tab ${isEventsRoute ? "active" : ""}`}
            onClick={() => navigate("/dashboard/security/events")}
          >
            Security Events
          </button>
          <button
            className={`btn secondary nav-tab ${isRevenueRoute ? "active" : ""}`}
            onClick={() => navigate("/dashboard/revenue-integrity/incidents")}
          >
            Revenue Integrity
          </button>
          <button
            className={`btn secondary nav-tab ${isPortfolioRoute ? "active" : ""}`}
            onClick={() => navigate("/dashboard/portfolio")}
          >
            Portfolio
          </button>
          <button
            className={`btn secondary nav-tab ${isWebsiteSettingsRoute ? "active" : ""}`}
            onClick={() => navigate("/dashboard/websites")}
          >
            Websites
          </button>
          <button
            className={`btn secondary nav-tab ${isOnboardingRoute ? "active" : ""}`}
            onClick={() => navigate("/dashboard/onboarding")}
          >
            Onboarding
          </button>
          <button
            className={`btn secondary nav-tab ${isHelpRoute ? "active" : ""}`}
            onClick={() => navigate("/dashboard/help")}
          >
            Help
          </button>
          <button
            className={`btn secondary nav-tab ${isIntegrationsRoute ? "active" : ""}`}
            onClick={() => navigate("/dashboard/integrations")}
          >
            Integrations
          </button>
          <button
            className={`btn secondary nav-tab ${isMarketplaceRoute ? "active" : ""}`}
            onClick={() => navigate("/dashboard/marketplace")}
          >
            Marketplace
          </button>
          <button
            className={`btn secondary nav-tab ${isComplianceRoute ? "active" : ""}`}
            onClick={() => navigate("/dashboard/compliance/audit")}
          >
            Compliance
          </button>
          <button
            className={`btn secondary nav-tab ${isAdminRoute && !isAdminStatusRoute ? "active" : ""}`}
            onClick={() => navigate("/admin")}
          >
            Admin
          </button>
          {isAdminRoute && (
            <button
              className={`btn secondary nav-tab ${isAdminStatusRoute ? "active" : ""}`}
              onClick={() => navigate("/admin/status")}
            >
              Status Ops
            </button>
          )}
          {isAdminRoute && (
            <button
              className={`btn secondary nav-tab ${isAdminActivationRoute ? "active" : ""}`}
              onClick={() => navigate("/admin/activation")}
            >
              Activation
            </button>
          )}
          {isAdminRoute && (
            <button
              className={`btn secondary nav-tab ${isAdminGrowthRoute ? "active" : ""}`}
              onClick={() => navigate("/admin/growth")}
            >
              Growth
            </button>
          )}
          {isAdminRoute && (
            <button
              className={`btn secondary nav-tab ${isAdminAffiliateRoute ? "active" : ""}`}
              onClick={() => navigate("/admin/affiliates")}
            >
              Affiliates
            </button>
          )}
          {isAdminRoute && (
            <button
              className={`btn secondary nav-tab ${isAdminMarketplaceRoute ? "active" : ""}`}
              onClick={() => navigate("/admin/marketplace")}
            >
              Templates
            </button>
          )}
          <button
            className={`btn secondary nav-tab ${isNotificationsRoute ? "active" : ""}`}
            onClick={() => navigate("/dashboard/settings/notifications")}
          >
            Notifications
          </button>
          <button
            className={`btn secondary nav-tab ${isBrandingRoute ? "active" : ""}`}
            onClick={() => navigate("/dashboard/settings/branding")}
          >
            Branding
          </button>
          <button
            className={`btn secondary nav-tab ${isReferralsRoute ? "active" : ""}`}
            onClick={() => navigate("/dashboard/referrals")}
          >
            Referrals
          </button>
          <button className="btn secondary" onClick={toggleTheme}>
            {isDark ? "Light mode" : "Dark mode"}
          </button>
          <button className="btn danger" onClick={handleLogout}>
            Logout
          </button>
        </div>
      </header>

      {isRemediationRoute ? (
        <RemediationWorkspacePage incidentId={remediationIncidentId} />
      ) : marketplaceId ? (
        <MarketplaceTemplateDetailPage templateId={marketplaceId} />
      ) : isMarketplaceRoute ? (
        <MarketplacePage />
      ) : isOnboardingRoute ? (
        <OnboardingWizardPage />
      ) : isHelpRoute ? (
        <DocsHubPage />
      ) : isIntegrationsRoute ? (
        <IntegrationsDirectoryPage />
      ) : isIncidentDetailRoute ? (
        <RevenueIntegrityIncidentDetailPage incidentId={incidentId} />
      ) : isWebsiteSettingsRoute ? (
        <WebsiteSettingsPage websiteId={websiteSettingsId} />
      ) : isLeaksRoute ? (
        <RevenueLeakHeatmapPage />
      ) : isRevenueRoute ? (
        <RevenueIntegrityIncidentsPage />
      ) : isMapRoute ? (
        <SecurityMapPage />
      ) : isEventsRoute ? (
        <SecurityEventsPage />
      ) : isNotificationsRoute ? (
        <NotificationsSettingsPage />
      ) : isBrandingRoute ? (
        <BrandingSettingsPage />
      ) : isPortfolioRoute ? (
        <PortfolioPage />
      ) : isReferralsRoute ? (
        <ReferralProgramPage />
      ) : isComplianceRoute ? (
        isComplianceRetentionRoute ? <ComplianceRetentionPage /> : <ComplianceAuditPage />
      ) : isAdminRoute ? (
        isAdminStatusRoute ? <AdminStatusPage /> : isAdminActivationRoute ? <AdminActivationPage /> : isAdminGrowthRoute ? <AdminGrowthPage /> : isAdminAffiliateRoute ? <AdminAffiliatePage /> : isAdminMarketplaceRoute ? <AdminMarketplacePage /> : <AdminConsolePage />
      ) : isBillingRoute ? (
        <BillingPage />
      ) : (
        <>
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
        </>
      )}
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
