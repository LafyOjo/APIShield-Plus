/*
# shop-ui/app.js — env-driven re-auth + multi-page UI
# ---------------------------------------------------
# This is the main frontend script powering the Demo Shop.
# It’s intentionally lightweight (vanilla JS + static HTML) so the
# security flows are easy to see. The UI supports server-driven re-auth
# flags, which lets me demo strict vs. relaxed policies without code edits.
*/


/*
# Core API & token keys live here so the rest of the code stays clean.
# API_BASE points at the demo shop; swapping it lets me point to prod/dev.
# TOKEN_KEY is a simple dashboard flag; AUTH_TOKEN_KEY is what requests read.
# Keeping these centralized avoids sprinkling magic strings around the codebase.
*/
const API_BASE = 'http://localhost:3005'; // served by demo-shop
const TOKEN_KEY = 'apiShieldAuthToken';   // dashboard token (optional)
const AUTH_TOKEN_KEY = 'apiShieldAuthToken';

/*
# Audit logging goes to the APIShield+ backend (port :8001 by default).
# If I’m on localhost, I rewrite the port; otherwise I consult an env var.
# This lets me deploy the shop anywhere and still have logs wired up.
# The AUDIT_URL is used by a tiny best-effort logger later in the file.
*/
const envAudit = (typeof process !== 'undefined' && process.env)
  ? process.env.REACT_APP_AUDIT_URL
  : undefined;
const AUDIT_BASE = window.location.hostname === 'localhost'
  ? API_BASE.replace(/:\d+/, ':8001')
  : envAudit || API_BASE.replace(/:\d+/, ':8001');
const AUDIT_URL = `${AUDIT_BASE}/api/audit/log`;

/*
# Some audit endpoints want an API key alongside the bearer token.
# For demos, I fall back to 'demo-key' so things “just work”.
# In production, this would be injected via a build variable.
# It keeps sensitive headers out of the main application code.
*/
const APISHIELD_KEY = window.APISHIELD_KEY || 'demo-key';

/*
# The server exposes a tiny JSON resource that mirrors .env flags.
# Reading /shop-config.json lets the UI decide if it should pre-prompt
# for the password on every sensitive action, or only on 401 retry.
# This pattern keeps policy in the backend, not hardcoded in the UI.
*/
const SHOP_CONFIG_URL = '/shop-config.json';
let SHOP_CONFIG = { reauthPerRequest: false, forceReauth: false };
let reauthRequired = false; // if true, prompt for password on protected calls

/*
# I track the logged-in username in memory after a successful login.
# It drives UI state (cart badge, login/logout visibility) and audit logs.
# This avoids re-fetching the session all the time and keeps the UI snappy.
# If the session drops, we clear it and the UI updates accordingly.
*/
let username = null;

//-------------------------------------------------------------
// Small helpers
//-------------------------------------------------------------

/*
# Tiny DOM helpers so I don’t repeat boilerplate everywhere.
# `$` wraps querySelector; `on` adds an event listener only if the element exists.
# These reduce footguns (null checks) and keep the main logic readable.
# They’re single-purpose by design, so the rest of the code stays intentional.
*/
function $(sel) { return document.querySelector(sel); }
function on(el, evt, handler) { if (el) el.addEventListener(evt, handler); }

/*
# setContent swaps the main content area with a small fade effect.
# I update innerHTML, then call an optional callback to bind events.
# This feels much nicer than hard page reloads and keeps state local.
# It’s a tiny SPA pattern without pulling in a full framework.
*/
function setContent(html, callback) {
  const el = document.getElementById('content');
  if (!el) return;
  el.style.opacity = 0;
  setTimeout(() => {
    el.innerHTML = html;
    el.style.opacity = 1;
    if (typeof callback === 'function') callback();
  }, 120);
}

/*
# showMessage is my lightweight toast for errors/notifications.
# It toggles classes for success/error, shows the text, then hides.
# A shared message system keeps feedback consistent across views.
# The short timeout keeps the UI fast and avoids modal fatigue.
*/
function showMessage(text, isError = false) {
  const msg = document.getElementById('message');
  if (!msg) return;
  msg.classList.toggle('alert-danger', isError);
  msg.classList.toggle('alert-success', !isError);
  msg.textContent = text;
  msg.style.display = 'block';
  setTimeout(() => { msg.style.display = 'none'; }, 1600);
}

//-------------------------------------------------------------
// Config loader — reflects .env via the server
//-------------------------------------------------------------

/*
# loadShopConfig pulls server-side flags that represent .env values.
# If the fetch fails, we keep safe defaults and don’t break the UI.
# The computed `reauthRequired` flips the UX between strict and relaxed.
# This keeps the demo flexible without redeploying the frontend.
*/
async function loadShopConfig() {
  try {
    const resp = await fetch(SHOP_CONFIG_URL, { credentials: 'include' });
    if (resp.ok) SHOP_CONFIG = await resp.json();
  } catch (_) {
    // keep defaults
  }
  reauthRequired = !!(SHOP_CONFIG.forceReauth || SHOP_CONFIG.reauthPerRequest);
}

// Unified fetch with (optional) per-request re-auth prompt


/*
# fetchJSON is my one opportunity for API calls: consistent headers, credentials,
# optional Authorization for audits, and the re-auth prompt.
# If strict mode is on, I pre-prompt for a password and add X-Reauth-Password.
# On a 401, I retry exactly once with a prompt.
*/
async function fetchJSON(url, options = {}) {
  const { noAuth, skipPromptOnce, ...opts } = options;
  const fetchOpts = {
    method: opts.method || 'GET',
    headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
    credentials: 'include',
    body: opts.body,
  };

  /*
  # Attach the dashboard token only to audit calls (backend may verify).
  # Shop auth flows are cookie/session or re-auth header based in this demo.
  # This keeps concerns separated: app logic vs. observability/logging.
  # If there’s no token, we simply omit the Authorization header.
  */
  const token = localStorage.getItem(AUTH_TOKEN_KEY);
  if (token && !fetchOpts.headers['Authorization']) {
    // Only used by AUDIT_URL (backend may ignore otherwise)
    if (url.startsWith('http') && url.includes(':8001')) {
      fetchOpts.headers['Authorization'] = `Bearer ${token}`;
    }
  }

  /*
  # If the environment wants per-request re-auth, we pre-prompt here.
  # The user can cancel, which we treat as Unauthorized to stop the flow.
  # Adding X-Reauth-Password makes the backend verify the password inline.
  # This is tedious by design—great for demonstrating friction-based security.
  */
  if (!noAuth && reauthRequired && !skipPromptOnce) {
    const pw = window.prompt('Please re-enter your password:');
    if (!pw) throw new Error('Unauthorized');
    fetchOpts.headers['X-Reauth-Password'] = pw;
  }

  /*
  # First attempt: make the request and catch network-level issues.
  # “Network error” here could be CORS, connectivity, or server down.
  # We don’t mask the failure; we convert it into a friendly exception.
  # That keeps calling code simple: try/catch around fetchJSON() is enough.
  */
  let res;
  try {
    res = await fetch(url, fetchOpts);
  } catch (e) {
    throw new Error('Network error');
  }

  /*
  # If the server returns 401 and we didn’t pre-prompt, offer one retry.
  # We ask for the password, attach X-Reauth-Password, and try again.
  # This mirrors how many apps do “step-up auth”: only when needed.
  # If it still fails, we bubble up Unauthorized so the UI can react.
  */
  if (res.status === 401 && !noAuth && !skipPromptOnce) {
    const pw = window.prompt('Please re-enter your password:');
    if (!pw) throw new Error('Unauthorized');
    const retry = { ...fetchOpts, headers: { ...fetchOpts.headers, 'X-Reauth-Password': pw } };
    res = await fetch(url, retry);
  }

  /*
  # Standard non-OK handling: pull the body text if present for clarity.
  # This helps debug HTTP 4xx/5xx without opening devtools every time.
  # If there’s no text, we still include the status code in the message.
  # The caller’s try/catch will show a toast and keep the UI alive.
  */
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(text || `Request failed: ${res.status}`);
  }

  /*
  # Not every endpoint returns JSON (some return 204/empty).
  # We sniff content-type and only parse JSON when it’s actually JSON.
  # This avoids throwing on successful but empty responses.
  # Returning {} for non-JSON keeps the call sites simple.
  */
  const ct = res.headers.get('content-type') || '';
  return ct.includes('application/json') ? res.json() : {};
}

// Best-effort audit helper

/*
# logAuditEvent sends a compact event payload to the audit backend.
# It’s deliberately “best effort”: failures are swallowed so the UX
# never suffers because of observability outages or network blips.
# We include an API key and a bearer when present for trust/replay checks.
*/
async function logAuditEvent(event) {
  try {
    const token = localStorage.getItem(AUTH_TOKEN_KEY);
    const headers = { 'Content-Type': 'application/json', 'X-API-Key': APISHIELD_KEY };
    if (token) headers['Authorization'] = `Bearer ${token}`;
    await fetch(AUDIT_URL, {
      method: 'POST',
      headers,
      body: JSON.stringify({ event, username }),
      credentials: 'include',
    });
  } catch (_) {}
}

// Catalog & cart

/*
# loadProducts renders the catalog grid, optionally filtered by category.
# I keep the hero visible only on the home view to make categories feel focused.
# Products are fetched from the API, transformed into cards, and injected.
# This is the main landing experience and stays un-authenticated by design.
*/
async function loadProducts(category) {
  const hero = document.getElementById('hero');
  if (hero) hero.style.display = category ? 'none' : 'block';
  const qs = category ? `?category=${encodeURIComponent(category)}` : '';
  const items = await fetchJSON(`${API_BASE}/products${qs}`, { noAuth: true, skipPromptOnce: true });
  const list = items.map(p => `

    <article class="product">
      <div class="img">
      <img src="${p.image}" 
      alt="${p.name}" 
      loading="lazy"/>
      </div>
      <div class="body">
        <div class="title">${p.name}</div>
        <div class="row"
        ><div class="price">£${p.price}</div>
        <button class="btn" onclick="addToCart(${p.id})">Add</button></div>
      </div>
    </article>
  `).join('');
  setContent(`
    <div class="stack">
      <div class="row" style="justify-content:space-between">
        <h2>${category ? (category[0].toUpperCase() + category.slice(1)) : 'Featured'}</h2>
        <div class="muted">${items.length} items</div>
      </div>
      <div class="grid">${list}</div>
    </div>
  `);
}

/*
# addToCart calls a protected endpoint; if you’re not logged in,
# it’ll fail and we’ll show a friendly message. On success we update
# the little cart badge so the UI stays in sync. Keeping this logic
# here avoids leaking auth checks into the rendering code above.
*/
async function addToCart(id) {
  try {
    await fetchJSON(`${API_BASE}/cart`, { method: 'POST', body: JSON.stringify({ productId: id }) });
    showMessage('Added to cart');
    updateCartCount();
  } catch (e) {
    showMessage('You must be logged in', true);
  }
}

/*
# viewCart renders a simple table of the cart contents. It’s protected,
# so a 401 will trigger our auth flow and show a helpful message.
# I keep the markup intentionally minimal so the focus stays on flows.
# The purchase button kicks off a protected POST to finalize the order.
*/
async function viewCart() {
  try {
    const items = await fetchJSON(`${API_BASE}/cart`);
    const rows = items.map(i => `<tr><td>${i.name}</td><td class="text-end">£${i.price}</td></tr>`).join('');
    setContent(`
      <div class="card">
        <h2>Your Cart</h2>
        <table class="table mb-3" id="cartItems">
          <thead><tr><th>Product</th><th class="text-end">Price</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
        <button class="btn" onclick="purchase()">Purchase</button>
      </div>
    `);
  } catch (e) {
    showMessage('You must be logged in', true);
  }
}

/*
# purchase hits a protected endpoint and, if successful, resets the UI:
# we show a success toast, refresh the cart badge, and return to products.
# There’s no real payment processing—this is a demo-only flow.
# It’s perfect for showcasing re-auth prompts on sensitive actions.
*/
async function purchase() {
  try {
    await fetchJSON(`${API_BASE}/purchase`, { method: 'POST' });
    showMessage('Purchase complete');
    updateCartCount();
    loadProducts();
  } catch (e) {
    showMessage('You must be logged in', true);
  }
}

// Profile

/*
# showProfile tries to load the current profile and prefill a form.
# If you’re not authenticated, it renders the form shell with a notice.
# This keeps the route stable and lets you log in without losing context.
# Saving the form is handled in fillProfileForm’s submit handler.
*/
async function showProfile() {
  try {
    const data = await fetchJSON(`${API_BASE}/profile`);
    const p = data.profile || {};
    fillProfileForm(p);
  } catch (e) {
    fillProfileForm({});
    const n = document.getElementById('profileNotice');
    if (n) { n.textContent = 'Please log in to edit profile'; n.style.display = 'block'; }
  }
}

/*
# fillProfileForm renders the profile edit UI and wires up the submit.
# I assemble a payload from the inputs and POST it to /profile.
# On success you get a simple toast; on failure we show an error.
# The layout stays humble so the security behavior is the star.
*/
function fillProfileForm(p) {
  const html = `
    <div class="card">
      <div id="profileNotice" class="alert alert-danger" style="display:none"></div>
      <h2>Profile</h2>
      <p class="muted" style="margin-top:-.25rem">Manage your contact & shipping details</p>
      <form class="form" id="profileForm">
        <div class="field"><label>Full name</label><input id="pf_name" value="${p.fullName || ''}"></div>
        <div class="field"><label>Email</label><input id="pf_email" value="${p.email || ''}"></div>
        <div class="field"><label>Phone</label><input id="pf_phone" value="${p.phone || ''}"></div>
        <div class="field"><label>Address line 1</label><input id="pf_a1" value="${p.address1 || ''}"></div>
        <div class="field"><label>Address line 2</label><input id="pf_a2" value="${p.address2 || ''}"></div>
        <div class="field"><label>City</label><input id="pf_city" value="${p.city || ''}"></div>
        <div class="field"><label>Postcode</label><input id="pf_pc" value="${p.postcode || ''}"></div>
        <div class="field"><label>Country</label><input id="pf_ctry" value="${p.country || ''}"></div>
        <div class="row"><button class="btn" type="submit">Save</button><span class="muted">${p.updatedAt ? `Updated ${new Date(p.updatedAt).toLocaleString()}` : ''}</span></div>
      </form>
    </div>`;
  setContent(html, () => {
    const form = document.getElementById('profileForm');
    on(form, 'submit', async (e) => {
      e.preventDefault();
      const body = {
        fullName: document.getElementById('pf_name').value,
        email: document.getElementById('pf_email').value,
        phone: document.getElementById('pf_phone').value,
        address1: document.getElementById('pf_a1').value,
        address2: document.getElementById('pf_a2').value,
        city: document.getElementById('pf_city').value,
        postcode: document.getElementById('pf_pc').value,
        country: document.getElementById('pf_ctry').value,
      };
      try {
        await fetchJSON(`${API_BASE}/profile`, { method: 'POST', body: JSON.stringify(body) });
        showMessage('Profile saved');
      } catch (_) {
        showMessage('Save failed', true);
      }
    });
  });
}

// Auth views

/*
# showLogin renders the login form and handles submit.
# We don’t pre-prompt for re-auth here—the server owns the login flow.
# After a successful login, we reload server config to pick up any policy.
# Then we flip the header UI (login/logout), update the cart badge, and land on products.
*/
function showLogin() {
  setContent(`
    <div class="card">
      <h2>Login</h2>
      <form id="loginForm" class="form">
        <div class="field"><label>Username</label><input id="username" required /></div>
        <div class="field"><label>Password</label><input id="pw" type="password" required /></div>
        <button class="btn" type="submit">Login</button>
      </form>
      <p class="muted">Demo credentials: <code>alice / secret</code></p>
      <p>Or <a href="#" id="registerLink">register</a></p>
    </div>
  `, () => {
    const form = document.getElementById('loginForm');
    on(form, 'submit', async (e) => {
      e.preventDefault();
      username = document.getElementById('username').value;
      const pw = document.getElementById('pw').value;
      try {
        // Do not pre-prompt here; server handles login
        await fetchJSON(`${API_BASE}/login`, {
          method: 'POST',
          body: JSON.stringify({ username, password: pw }),
          noAuth: true,
          skipPromptOnce: true,
        });
        // After login, refresh server-driven config
        await loadShopConfig();
        const lb = document.getElementById('loginBtn');
        const lo = document.getElementById('logoutBtn');
        if (lb) lb.style.display = 'none';
        if (lo) lo.style.display = 'inline-block';
        updateCartCount();
        loadProducts();
      } catch (_) {
        showMessage('Login failed', true);
        username = null;
      }
    });
    const reg = document.getElementById('registerLink');
    on(reg, 'click', (e) => { e.preventDefault(); showRegister(); });
  });
}

/*
# showRegister keeps the flow symmetrical with login.
# We create the account via /register and then nudge the user to log in.
# Same `skipPromptOnce` to avoid any re-auth prompt during registration.
# This is a small but complete demo of an end-to-end auth journey.
*/
function showRegister() {
  setContent(`
    <div class="card">
      <h2>Register</h2>
      <form id="regForm" class="form">
        <div class="field"><label>Username</label><input id="regUser" required /></div>
        <div class="field"><label>Password</label><input id="regPw" type="password" required /></div>
        <button type="submit" class="btn">Create account</button>
      </form>
    </div>
  `, () => {
    const form = document.getElementById('regForm');
    on(form, 'submit', async (e) => {
      e.preventDefault();
      const u = document.getElementById('regUser').value;
      const pw = document.getElementById('regPw').value;
      try {
        await fetchJSON(`${API_BASE}/register`, {
          method: 'POST',
          body: JSON.stringify({ username: u, password: pw }),
          noAuth: true,
          skipPromptOnce: true,
        });
        showMessage('Registered! Please log in.');
        showLogin();
      } catch (_) {
        showMessage('Registration failed', true);
      }
    });
  });
}

/*
# checkSession asks the backend if we’re logged in and updates the header.
# It toggles the login/logout buttons and stores the username for later.
# If the call fails for any reason, we fall back to a logged-out state.
# The cart badge is refreshed at the end to keep the header accurate.
*/
async function checkSession() {
  try {
    const data = await fetchJSON(`${API_BASE}/session`, { noAuth: true, skipPromptOnce: true });
    const lb = document.getElementById('loginBtn');
    const lo = document.getElementById('logoutBtn');
    if (data.loggedIn) {
      username = data.username;
      if (lb) lb.style.display = 'none';
      if (lo) lo.style.display = 'inline-block';
    } else {
      username = null;
      if (lb) lb.style.display = 'inline-block';
      if (lo) lo.style.display = 'none';
    }
  } catch (_) {
    username = null;
    const lb = document.getElementById('loginBtn');
    const lo = document.getElementById('logoutBtn');
    if (lb) lb.style.display = 'inline-block';
    if (lo) lo.style.display = 'none';
  }
  updateCartCount();
}

/*
# logout calls the server to clear the session, logs an audit event,
# and resets the UI back to a clean logged-out state. We then refresh
# the cart count and reload products so the page feels consistent.
# Any errors in the logout call are swallowed for a smooth experience.
*/
async function logout() {
  try {
    await fetchJSON(`${API_BASE}/logout`, { method: 'POST', noAuth: true, skipPromptOnce: true });
  } catch (_) {}
  await logAuditEvent('user_logout');
  username = null;
  const lb = document.getElementById('loginBtn');
  const lo = document.getElementById('logoutBtn');
  if (lb) lb.style.display = 'inline-block';
  if (lo) lo.style.display = 'none';
  updateCartCount();
  loadProducts();
}

/*
# updateCartCount is a tiny convenience that keeps the cart badge correct.
# If we’re logged out or the API call fails, we reset to zero.
# This runs after actions that could mutate the cart (add/purchase).
# It keeps the header state honest without full page reloads.
*/
async function updateCartCount() {
  const badge = document.getElementById('cartCount');
  if (!badge) return;
  if (!username) { badge.textContent = 0; return; }
  try {
    const items = await fetchJSON(`${API_BASE}/cart`);
    badge.textContent = items.length;
  } catch (_) {
    badge.textContent = 0;
  }
}

// Static sections

/*
# These are simple static content views. They swap the content area
# with pre-built markup and require no API calls. Keeping them here
# makes navigation feel complete without adding framework overhead.
# It's a nice way to show and seperate some HTML files
*/
function showServices() {
  setContent(`
    <div class="card">
      <h2>Our Services</h2>
      <ul class="stack">
        <li>Gift wrapping</li>
        <li>Premium support</li>
        <li>Express shipping</li>
      </ul>
    </div>
  `);
}

function showAbout() {
  setContent(`
    <div class="card">
      <h2>About Us</h2>
      <p class="muted">Demo Shop is a tiny storefront used to showcase API security features.</p>
      <p>No real payments are processed.</p>
    </div>
  `);
}

function showContact() {
  setContent(`
    <div class="card">
      <h2>Contact Us</h2>
      <p>Email: <a href="mailto:support@example.com">support@example.com</a></p>
      <p>Phone: 555-1234</p>
    </div>
  `);
}

/*
# viewStats is a tiny “admin-ish” view that reads per-user API call counts.
# It’s meant to hint at how analytics can surface suspicious patterns
# (like credential stuffing). The UI is intentionally humble—just a list.
# It rounds out the demo story without dragging in a charting library.
*/
async function viewStats() {
  try {
    const data = await fetchJSON(`${API_BASE}/api-calls`);
    const list = Object.entries(data).map(([user, count]) => `<li>${user}: ${count}</li>`).join('');
    setContent(`<div class="card"><h2>API Calls</h2><ul class="stack">${list}</ul></div>`);
  } catch (_) {
    showMessage('Failed to load stats', true);
  }
}

// Init

/*
# init wires up navigation, loads server config, and draws the homepage.
# I expose a couple functions on window for inline handlers (addToCart/purchase).
# There’s also a tiny interval watching the dashboard token so multi-tab flows
# stay in sync. Doing config first ensures re-auth behavior is correct from the start.
*/
async function init() {
  await loadShopConfig(); // must be first so reauth behavior is known

  on(document.getElementById('homeBtn'), 'click', () => loadProducts());
  on(document.getElementById('menBtn'), 'click', () => loadProducts('men'));
  on(document.getElementById('womenBtn'), 'click', () => loadProducts('women'));
  on(document.getElementById('accessBtn'), 'click', () => loadProducts('access'));
  on(document.getElementById('aboutBtn'), 'click', showAbout);
  on(document.getElementById('cartBtn'), 'click', viewCart);
  on(document.getElementById('loginBtn'), 'click', showLogin);
  on(document.getElementById('logoutBtn'), 'click', logout);
  on(document.getElementById('statsBtn'), 'click', viewStats);
  on(document.getElementById('servicesBtn'), 'click', showServices);
  on(document.getElementById('contactBtn'), 'click', showContact);
  on(document.getElementById('profileBtn'), 'click', showProfile);
  on(document.getElementById('shopMenBtn'), 'click', () => loadProducts('men'));
  on(document.getElementById('shopWomenBtn'), 'click', () => loadProducts('women'));

  // Expose needed functions for inline handlers
  window.addToCart = addToCart;
  window.purchase = purchase;

  loadProducts();
  checkSession();

  // Watch for dashboard token changes (audit auth only)
  let lastToken = localStorage.getItem(AUTH_TOKEN_KEY);
  setInterval(() => {
    const current = localStorage.getItem(AUTH_TOKEN_KEY);
    if (current !== lastToken) {
      lastToken = current;
    }
  }, 1000);
}

/*
# DOM ready technique: if the document is still loading,
# wait for page and the elements to load. Otherwise, fire init immediately.
# This avoids race conditions where elements aren’t yet available and then errors start appearing on the dashboard.
# It’s the small glue that keeps the app consistently booting.
*/
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
