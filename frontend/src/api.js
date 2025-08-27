/*
# frontend/src/api.js

# This module holds all API calls and authentication behavior for the app. I keep environment-driven bits (base URL, API key) here so the UI code
# can stay clean. Re-auth prompts, token headers, and error handling all  live in one place, which makes the rest of the app simple to reason about.
*/

/*
# API_BASE decides where requests go. If the env var is set, I filter it
# by stripping any trailing slash so I don’t get double slashes later.
# If it’s not set, I default to an empty string, which lets CRA’s proxy
# handle routing during local development without me needing absolute URLs.
*/
export const API_BASE =
  (process.env.REACT_APP_API_BASE && process.env.REACT_APP_API_BASE.replace(/\/$/, "")) || "";
export const API_KEY = process.env.REACT_APP_API_KEY || process.env.ZERO_TRUST_API_KEY || "";
export const AUTH_TOKEN_KEY = "apiShieldAuthToken";
export const TOKEN_KEY = AUTH_TOKEN_KEY; // legacy alias
export const USERNAME_KEY = "apiShieldUsername";

let FORCE_REAUTH_EVERY_CLICK = false; // global switch

/*
# setForceReauthEveryClick(enable)
# This simple setter lets the app enable/disable global pre-prompts.
# I call it once in app startup if I want a prompt on every click.
# It’s intentionally minimal: store a boolean, and let apiFetch read it.
# Small knobs like this make security behavior easy to experiment with.
*/
export function setForceReauthEveryClick(enable) {
  FORCE_REAUTH_EVERY_CLICK = !!enable;
}


/*
# logAuditEvent(event, username)
# Fire-and-forget audit logging. I attach an event name and, if present,
# the username. This intentionally swallows failures because observability
# should never break primary UX. Under the hood it uses apiFetch, but we
# set skipReauth so background logs don’t nag for a password.
*/
export async function logAuditEvent(event, username) {
  try {
    const payload = { event };
    if (username) payload.username = username;
    await apiFetch("/api/audit/log", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      // don't force/trigger prompts for background logging
      skipReauth: true,
    });
  } catch (err) {
    // Fail silently; audit logging should not disrupt UX
    console.error("audit log failed", err);
  }
}

/*
# This clears both the token and the cached username, then reloads the page
# to reset any in-memory state. As a nice touch, I try to log an audit event
# first if a token/username existed. Reloading is the most reliable way to
# ensure every component re-renders in a clean, logged-out state.
*/
export function logout() {
  const token = localStorage.getItem(AUTH_TOKEN_KEY);
  const username = localStorage.getItem(USERNAME_KEY);
  if (token) {
    // best effort
    logAuditEvent("user_logout", username);
  }
  localStorage.removeItem(AUTH_TOKEN_KEY);
  if (username) localStorage.removeItem(USERNAME_KEY);
  // simplest: reload the app to clear any in-memory state
  window.location.reload();
}

/*
# This is the single door for network calls. It normalizes headers,
# adds Authorization and X-API-Key when present, supports “pre-prompt”
# re-auth (FORCE_REAUTH_EVERY_CLICK or per-call), and will retry once
# on a 401 by prompting the user. Callers get a familiar fetch Response.
#
# Options:
#  - skipReauth: don’t prompt on 401 (great for polling/background)
#  - forceReauth: prompt BEFORE the first attempt (great for user actions)
#  - plus all native fetch options like method/headers/body, etc.
*/
export async function apiFetch(path, options = {}) {
  const {
    skipReauth = false,
    forceReauth = false,
    // any other native fetch options:
    ...fetchOptions
  } = options;

  /*
  # Build the final URL. I accept both absolute and relative paths so that
  # callers can override API_BASE on a one-off basis if needed. Headers are
  # initialized from the caller but I’ll add auth and keys below. This lets
  # app code remain declarative while security concerns stay centralized.
  */
  const url = path.startsWith("http") ? path : `${API_BASE}${path}`;
  const headers = { ...(fetchOptions.headers || {}) };

  /*
  # Some endpoints should never include Authorization or trigger a prompt.
  # These are the auth bootstrap endpoints: login, register, token minting.
  # Keeping this list here means the rest of the codebase doesn’t need to
  # special-case these calls—it just works without surprises.
  */
  const skipAuth =
    url.endsWith("/login") ||
    url.endsWith("/register") ||
    url.endsWith("/api/token");

  /*
  # If we have a JWT stored, attach it unless the endpoint is in the skip list.
  # I also avoid overwriting a caller-supplied Authorization header, which gives
  # advanced use-cases an escape hatch (e.g., service-to-service calls).
  # This keeps token propagation simple and predictable.
  */
  const token = localStorage.getItem(AUTH_TOKEN_KEY);
  if (token && !skipAuth && !("Authorization" in headers)) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  /*
  # Zero Trust / API gateway key. If configured, I add it to all requests
  # unless the caller explicitly set their own. This header helps demo
  # scenarios where network-level policy is enforced in addition to JWTs.
  # Combining the two gives a layered defense story.
  */
  if (API_KEY && !("X-API-Key" in headers)) {
    headers["X-API-Key"] = API_KEY;
  }

  /*
  # Pre-prompt path: if the global flag is on or the caller requests it,
  # I’ll ask the user for their password before the first attempt and add
  # X-Reauth-Password. If they cancel, I log them out for safety and return
  # a synthetic 401-like Response so callers can handle it gracefully.
  */
  if (!skipAuth && !skipReauth && (forceReauth || FORCE_REAUTH_EVERY_CLICK)) {
    const pw = window.prompt("Please re-enter your password:");
    if (!pw) {
      logout();
      // Return a synthetic 401-like Response so callers can handle it gracefully
      return new Response(null, { status: 401, statusText: "Unauthorized" });
    }
    headers["X-Reauth-Password"] = pw;
  }

  /*
  # First attempt goes out here. Network-level failures (offline, DNS, CORS)
  # are thrown so the caller can decide how to present errors (usually a toast).
  # I don’t swallow them because silent failures are a debugging nightmare.
  # The goal is to make network issues visible but easy to recover from.
  */
  let resp;
  try {
    resp = await fetch(url, { ...fetchOptions, headers });
  } catch (networkErr) {
    // Bubble up network errors to the caller (they usually show a toast)
    throw networkErr;
  }

  /*
  # If we didn’t get a 401 (or we purposely skipped auth/prompt), we’re done.
  # Returning the raw Response object keeps this function flexible—callers
  # can parse JSON, stream bodies, or read headers as needed. No surprises.
  # Only the 401 path below gets special handling.
  */
  if (resp.status !== 401 || skipAuth || skipReauth) {
    return resp;
  }

  /*
  # 401 path: one polite retry. I prompt the user for their password,
  # attach X-Reauth-Password, and try again. If they cancel, I log out
  # and hand back the original 401 so the caller can act accordingly.
  # This mirrors “step-up auth” in many real products.
  */
  const pw = window.prompt("Please re-enter your password:");
  if (!pw) {
    logout();
    return resp;
  }

  /*
  # Second attempt with the re-auth header included. If we still get 401,
  # I log out to clear any bad state (expired tokens, revoked sessions)
  # so the app comes back in a known-good logged-out state. This avoids
  # subtle bugs where the UI thinks you’re logged in but the server disagrees.
  */
  const retryHeaders = { ...headers, "X-Reauth-Password": pw };
  const retryResp = await fetch(url, { ...fetchOptions, headers: retryHeaders });

  // If still unauthorized after supplying password, log out to reset state
  if (retryResp.status === 401) {
    logout();
  }

  return retryResp;
}
