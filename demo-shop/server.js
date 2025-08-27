/* ------------------------------------------------------------
 * Demo Shop server — APIShield+ integrated
 * ------------------------------------------------------------
 * This tiny Express app powers a demo storefront and shows how
 * to wire a UI into an API security backend. Think “login, cart,
 * profile” — with calls out to APIShield+ to allow/deny access.
 * ------------------------------------------------------------ */

const express = require('express');
const session = require('express-session');
const bodyParser = require('body-parser');
const axios = require('axios');
const path = require('path');
const { spawn } = require('child_process');
const cors = require('cors');
const fetch = require('node-fetch');

const app = express();

/* ------------------------------------------------------------
 * Environment setup — sensible defaults for local dev.
 * We keep all knobs in env vars so you can point this demo
 * at different backends without touching the code. Timeouts,
 * keys, and feature flags all live here.
 * ------------------------------------------------------------ */
const PORT = process.env.PORT || 3005;
const API_BASE = process.env.API_BASE || 'http://127.0.0.1:8001';
const APISHIELD_URL = process.env.APISHIELD_URL || API_BASE;
const API_TIMEOUT = parseInt(process.env.API_TIMEOUT_MS || '10000', 10);
const API_KEY = process.env.API_KEY || '';
const FORWARD_API = process.env.FORWARD_API === 'true';
const REAUTH_PER_REQUEST = process.env.REAUTH_PER_REQUEST === 'true';

/* ------------------------------------------------------------
 * Axios defaults — apply a global timeout and optional API key.
 * This way every call we make to the backend inherits the same
 * safety rails, and we don’t repeat ourselves on each request.
 * ------------------------------------------------------------ */
axios.defaults.timeout = API_TIMEOUT;
if (API_KEY) {
  axios.defaults.headers.common['X-API-Key'] = API_KEY;
}

/* ------------------------------------------------------------
 * CORS comes first — allow the React app on localhost to talk
 * to this server. We keep it tight to specific origins and
 * include credentials so sessions work cross-origin in dev.
 * ------------------------------------------------------------ */
app.use(
  cors({
    origin: [
      'http://localhost:3000',
      'http://127.0.0.1:3000',
    ],
    credentials: true,
    allowedHeaders: ['Content-Type', 'Authorization', 'X-API-Key', 'X-Reauth-Password'],
    methods: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
  })
);

/* ------------------------------------------------------------
 * Core middleware — JSON body parsing and cookie-backed sessions.
 * This is intentionally simple: a shared secret and lax cookies
 * are enough for a demo, but you’d harden this for production.
 * ------------------------------------------------------------ */
app.use(bodyParser.json());
app.use(
  session({
    secret: 'demo-secret',
    resave: false,
    saveUninitialized: true,
    cookie: { sameSite: 'lax' },
  })
);

/* ------------------------------------------------------------
 * Static frontend — serves the shop UI straight from disk.
 * Visiting “/” loads index.html so you can poke around the
 * app without a separate web server.
 * ------------------------------------------------------------ */
app.use(express.static(path.join(__dirname, '../shop-ui')));

/* ------------------------------------------------------------
 * Helper: clientIp — best-effort way to figure out who’s calling.
 * We prefer X-Forwarded-For if present (behind proxies), and fall
 * back to Express’s “req.ip” so we always have something.
 * ------------------------------------------------------------ */
function clientIp(req) {
  const xfwd = req.headers['x-forwarded-for'];
  if (xfwd) return String(xfwd).split(',')[0].trim();
  return req.ip;
}

/* ------------------------------------------------------------
 * Helper: sendAuthEvent — fire-and-forget telemetry to APIShield+.
 * This keeps the security dashboard in the loop about what the
 * shop is seeing, without blocking the user experience.
 * ------------------------------------------------------------ */
async function sendAuthEvent({ user, action, success, source }) {
  try {
    await fetch(`${APISHIELD_URL}/events/auth`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(API_KEY ? { 'X-API-Key': API_KEY } : {}),
      },
      body: JSON.stringify({ user, action, success, source }),
    });
  } catch (e) {
    console.error('Failed to send auth event:', e.message);
  }
}

/* ------------------------------------------------------------
 * Guard: requireAuth — ensures the user is logged in, and if the
 * “reauth per request” flag is on, prompts for the password on
 * each protected action. Great for simulating tighter controls.
 * ------------------------------------------------------------ */
function requireAuth(req, res, next) {
  if (!req.session.username) return res.status(401).json({ error: 'Unauthorized' });
  if (REAUTH_PER_REQUEST) {
    const pw = req.get('X-Reauth-Password');
    if (!pw || pw !== req.session.password) {
      return res.status(401).json({ error: 'Reauthentication failed' });
    }
  }
  next();
}

/* ------------------------------------------------------------
 * Demo catalog — a tiny set of products with categories and
 * images. It’s static on purpose so your focus is on security,
 * not inventory management or databases.
 * ------------------------------------------------------------ */
const products = [
    { id: 1,  name: 'Tree Runner NZ',      price: 110, category: 'men',    image: "https://assets.levelshoes.com/cdn-cgi/image/width=720,height=1008,quality=85,format=webp/media/catalog/product/a/1/a11959-megrbl_7.jpg?ts=20250805043055"},
  { id: 2,  name: 'Tree Runner Cruiser', price: 110, category: 'women',  image: 'https://www.allbirds.co.uk/cdn/shop/files/TR2MNNT_SHOE_LEFT_GLOBAL_MENS_TREE_RUNNER_NAVY_NIGHT_DARK_NAVY.png?v=1751166585&width=1024g' },
  { id: 3,  name: 'Wool Runner MZ',      price: 120, category: 'men',    image: 'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQ6xHSVtr764EskA7jgprQ26WCSPsCzd5DI-g&s' },
  { id: 4,  name: 'Womens Nike Air Max',    price: 120, category: 'women',  image: 'https://lovellcdn.b-cdn.net/products/568021.jpg?width=700' },
  { id: 5,  name: 'Everyday No-Show',    price: 14,  category: 'access', image: 'https://cdn2.smartwool.filoblu.com/media/catalog/product/cache/25162cc576cf81151d28507649e6339b/s/m/smartwool_SW0019940691_01.jpg' },
  { id: 6,  name: 'Everyday Ankle',      price: 16,  category: 'access', image: 'https://cdn.fabletics.com/media/images/products/SC2354895-9366/SC2354895-9366-1_271x407.jpg?t=1710867919752' },
  { id: 7,  name: 'Trino™ Tee',          price: 35,  category: 'men',    image: 'https://www.schoffelcountry.com/cdn/shop/files/schoffel-mens-trevone-t-shirt-olive-green-cutout-front-01.png?v=1720004792&width=2000' },
  { id: 8,  name: 'Trino™ Tee W',        price: 35,  category: 'women',  image: 'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSuTVbShsKVi6EC_Nr12ae-44ULB07UFEDchg&s' },
  { id: 9,  name: 'Everyday Cap',        price: 22,  category: 'access', image: 'https://hatstore.imgix.net/886947030887_1.jpg?auto=compress%2Cformat&w=717&h=574&fit=crop&q=80' },
  { id: 10, name: 'Wool Hoodie',         price: 95,  category: 'men',    image: 'https://universalworks.co.uk/cdn/shop/files/p31212-wool-fleece-indigo_6046e8dd-b870-4be5-96c8-d1fd4993961a.jpg?v=1753707368&width=2000' },
  { id: 11, name: 'Wool Hoodie W',       price: 95,  category: 'women',  image: 'https://xcdn.next.co.uk/common/items/default/default/itemimages/3_4Ratio/product/lge/F17115s.jpg?im=Resize,width=750' },
  { id: 12, name: 'Sport Duffel',        price: 55,  category: 'access', image: 'https://contents.mediadecathlon.com/p2956361/k$0581f0916e83f54b2688966dc8631d63/picture.jpg?format=auto&f=3000x0' },
];

/* ------------------------------------------------------------
 * Seed user — “alice / secret” out of the box. This keeps the
 * demo smooth, since you don’t need to register just to try the
 * app. Everything is in-memory for simplicity.
 * ------------------------------------------------------------ */
const users = {
  alice: {
    password: 'secret',
    cart: [],
    profile: {
      fullName: 'Alice Doe',
      email: 'alice@example.com',
      phone: '',
      address1: '1 Demo Street',
      address2: '',
      city: 'Sampleville',
      postcode: 'AB1 2CD',
      country: 'UK',
      updatedAt: new Date().toISOString(),
    },
  },
};

/* ------------------------------------------------------------
 * Auth: /register — basic username/password signup. In demo mode
 * this lives in memory, but we optionally forward the same call
 * to APIShield so it sees the event too.
 * ------------------------------------------------------------ */
app.post('/register', async (req, res) => {
  const { username, password } = req.body || {};
  if (!username || !password) return res.status(400).json({ error: 'missing' });
  if (users[username]) return res.status(409).json({ error: 'exists' });

  users[username] = {
    password,
    cart: [],
    profile: { fullName: '', email: '', phone: '', address1: '', address2: '', city: '', postcode: '', country: '' },
  };

  if (FORWARD_API) {
    try { await axios.post(`${API_BASE}/register`, { username, password }); } catch { console.error('Register API call failed'); }
    try { await axios.post(`${API_BASE}/api/audit/log`, { event: 'user_register', username }); } catch { console.error('Audit log failed'); }
  }

  res.json({ status: 'ok' });
});

/* ------------------------------------------------------------
 * Auth: /login — validates credentials locally, but also consults
 * APIShield’s /score before issuing a session. If the risk engine
 * says “blocked”, we deny the login even if the password is right.
 * ------------------------------------------------------------ */
app.post('/login', async (req, res) => {
  const { username, password } = req.body || {};
  const ok = !!users[username] && users[username].password === password;

  // Telemetry is sent for both success and failure so the
  // dashboard can see the full picture of activity.
  sendAuthEvent({ user: username || null, action: 'demo-shop', success: !!ok, source: 'demo-shop' });

  // Wrong credentials — nudge APIShield (for stats) and return 401.
  if (!ok) {
    if (FORWARD_API) {
      try { await axios.post(`${API_BASE}/login`, { username, password }); } catch (e) { if (e.response?.status !== 401) console.error('Login API call failed'); }
      try { await axios.post(`${API_BASE}/score`, { client_ip: clientIp(req), auth_result: 'failure', with_jwt: false }); } catch { console.error('Score API call failed'); }
      try { await axios.post(`${API_BASE}/api/audit/log`, { event: 'user_login_failure', username }); } catch { console.error('Audit log failed'); }
    }
    return res.status(401).json({ error: 'invalid credentials' });
  }

  // Correct credentials — ask APIShield if we should allow it.
  if (FORWARD_API) {
    try {
      const decision = await axios.post(
        `${API_BASE}/score`,
        { client_ip: clientIp(req), auth_result: 'success', with_jwt: false },
        { timeout: API_TIMEOUT }
      );
      if (decision.data?.status === 'blocked') {
        try { await axios.post(`${API_BASE}/api/audit/log`, { event: 'user_login_blocked', username }); } catch {}
        return res.status(429).json({ error: 'blocked_by_security' });
      }
    } catch (e) {
      console.error('Score API call failed', e.message);
      // If you want to be strict, you could deny here when
      // the risk engine is unavailable. Left open for demo.
      // return res.status(503).json({ error: 'risk_engine_unavailable' });
    }
  }

  // Give the user a session — and optionally grab a backend token.
  req.session.username = username;
  req.session.password = password;

  if (FORWARD_API) {
    try {
      const apiResp = await axios.post(`${API_BASE}/login`, { username, password });
      req.session.apiToken = apiResp.data.access_token;
    } catch { console.error('Backend login failed'); }
    try { await axios.post(`${API_BASE}/api/audit/log`, { event: 'user_login_success', username }); } catch { console.error('Audit log failed'); }
  }

  res.json({ status: 'ok' });
});

/* ------------------------------------------------------------
 * Auth: /logout — mirrors the login flow by informing the backend
 * and then clearing the local session. We also emit telemetry so
 * the dashboard reflects user sign-out events.
 * ------------------------------------------------------------ */
app.post('/logout', async (req, res) => {
  if (FORWARD_API && req.session.apiToken) {
    try {
      await axios.post(`${API_BASE}/logout`, null, { headers: { Authorization: `Bearer ${req.session.apiToken}` } });
    } catch (e) { console.error('Backend logout failed', e.message); }
  }
  if (FORWARD_API) {
    try { await axios.post(`${API_BASE}/api/audit/log`, { event: 'user_logout', username: req.session.username }); } catch {}
  }
  const username = req.session.username;
  req.session.apiToken = null;
  req.session.destroy(err => {
    sendAuthEvent({ user: username || null, action: 'demo-shop', success: !err, source: 'demo-shop' });
    if (err) return res.status(500).json({ status: 'error' });
    res.json({ status: 'ok' });
  });
});

/* ------------------------------------------------------------
 * Profile: GET /profile — returns the current user’s profile.
 * We store it in memory to keep things simple, and require auth
 * so anonymous users can’t read account details.
 * ------------------------------------------------------------ */
app.get('/profile', requireAuth, (req, res) => {
  const u = users[req.session.username];
  res.json({ username: req.session.username, profile: u.profile || {} });
});

/* ------------------------------------------------------------
 * Profile: POST /profile — updates user fields and stamps an
 * “updatedAt”. Optionally logs an audit event to APIShield so
 * changes are visible on the security side.
 * ------------------------------------------------------------ */
app.post('/profile', requireAuth, async (req, res) => {
  const cur = users[req.session.username];
  cur.profile = { ...cur.profile, ...(req.body || {}), updatedAt: new Date().toISOString() };
  if (FORWARD_API) {
    try { await axios.post(`${API_BASE}/api/audit/log`, { event: 'profile_update', username: req.session.username }); } catch {}
  }
  res.json({ status: 'ok', profile: cur.profile });
});

/* ------------------------------------------------------------
 * Catalog: GET /products — returns all items or filters by the
 * “category” query param. It’s a lightweight, zero-DB endpoint,
 * perfect for demos and local tinkering.
 * ------------------------------------------------------------ */
app.get('/products', (req, res) => {
  const { category } = req.query; // men | women | access
  const list = category ? products.filter(p => p.category === String(category)) : products;
  res.json(list);
});

/* ------------------------------------------------------------
 * Cart: POST /cart — adds a product by ID to the user’s cart.
 * This is a protected action, so it flows through requireAuth
 * and (optionally) the per-request re-auth prompt.
 * ------------------------------------------------------------ */
app.post('/cart', requireAuth, (req, res) => {
  const { productId } = req.body || {};
  const product = products.find(p => p.id === productId);
  if (!product) return res.status(404).json({ error: 'not found' });
  users[req.session.username].cart.push(product);
  res.json({ status: 'added' });
});

/* ------------------------------------------------------------
 * Cart: GET /cart — returns the current user’s pending items.
 * Again, we keep it in the session for ease of demonstration
 * and to avoid bringing in a database.
 * ------------------------------------------------------------ */
app.get('/cart', requireAuth, (req, res) => {
  res.json(users[req.session.username].cart);
});

/* ------------------------------------------------------------
 * Cart: POST /purchase — clears the cart as if a purchase was
 * completed. This is intentionally barebones to focus your time
 * on the security behaviour rather than payment flows.
 * ------------------------------------------------------------ */
app.post('/purchase', requireAuth, (req, res) => {
  users[req.session.username].cart = [];
  res.json({ status: 'purchased' });
});

/* ------------------------------------------------------------
 * Session indicator — lets the frontend know whether it already
 * has an authenticated session. Helpful for rendering the right
 * navigation state on first load.
 * ------------------------------------------------------------ */
app.get('/session', (req, res) => {
  if (req.session.username) return res.json({ loggedIn: true, username: req.session.username });
  res.json({ loggedIn: false });
});

/* ------------------------------------------------------------
 * API call proxy — optionally asks APIShield for per-user call
 * counts and returns them to the UI. Requires a backend token
 * that we stuffed into the session during login.
 * ------------------------------------------------------------ */
app.get('/api-calls', requireAuth, async (req, res) => {
  if (!req.session.apiToken) return res.status(401).json({ error: 'no api token' });
  if (!FORWARD_API) return res.json({});
  try {
    const resp = await axios.get(`${API_BASE}/api/user-calls`, {
      headers: { Authorization: `Bearer ${req.session.apiToken}` },
    });
    res.json(resp.data);
  } catch (e) {
    console.error('User call fetch failed');
    res.status(500).json({ error: 'failed' });
  }
});

/* ------------------------------------------------------------
 * Server start — listen on the chosen port and try to open a
 * browser tab for convenience. If that fails, we just log and
 * keep running.
 * ------------------------------------------------------------ */
app.listen(PORT, () => {
  console.log(`Demo shop running on port ${PORT}`);
  const url = `http://localhost:${PORT}/`;
  const cmd = process.platform === 'win32' ? 'start' : process.platform === 'darwin' ? 'open' : 'xdg-open';
  try {
    const child = spawn(cmd, [url], { stdio: 'ignore', detached: true });
    child.on('error', () => {});
    child.unref();
  } catch {}
});
