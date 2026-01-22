const express = require('express');
const crypto = require('crypto');
require('dotenv').config();

const app = express();
const PORT = parseInt(process.env.PORT || '3006', 10);
const APP_URL = process.env.APP_URL || `http://localhost:${PORT}`;
const SHOPIFY_API_KEY = process.env.SHOPIFY_API_KEY || '';
const SHOPIFY_API_SECRET = process.env.SHOPIFY_API_SECRET || '';
const SHOPIFY_SCOPES = process.env.SHOPIFY_SCOPES || 'read_themes,write_themes';
const API_BASE_URL_DEFAULT = process.env.API_BASE_URL || '';
const AGENT_URL_DEFAULT = process.env.AGENT_URL || '';

if (typeof fetch !== 'function') {
  throw new Error('Node 18+ required (global fetch missing).');
}

app.use(express.urlencoded({ extended: false }));
app.use(express.json());

const pendingStates = new Map();
const shopStore = new Map();

function normalizeShop(shop) {
  if (!shop) return '';
  const value = String(shop).trim().toLowerCase();
  if (!/^[a-z0-9][a-z0-9-]*\.myshopify\.com$/.test(value)) {
    return '';
  }
  return value;
}

function buildIngestUrl(apiBaseUrl) {
  if (!apiBaseUrl) return '';
  return apiBaseUrl.replace(/\/+$/, '') + '/api/v1/ingest/browser';
}

function safeEqual(a, b) {
  const left = Buffer.from(String(a));
  const right = Buffer.from(String(b));
  if (left.length !== right.length) return false;
  return crypto.timingSafeEqual(left, right);
}

function verifyHmac(query) {
  const { hmac, ...rest } = query;
  if (!hmac) return false;
  const message = Object.keys(rest)
    .sort()
    .map((key) => `${key}=${Array.isArray(rest[key]) ? rest[key].join(',') : rest[key]}`)
    .join('&');
  const digest = crypto.createHmac('sha256', SHOPIFY_API_SECRET).update(message).digest('hex');
  return safeEqual(digest, hmac);
}

async function exchangeAccessToken(shop, code) {
  const resp = await fetch(`https://${shop}/admin/oauth/access_token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      client_id: SHOPIFY_API_KEY,
      client_secret: SHOPIFY_API_SECRET,
      code,
    }),
  });
  if (!resp.ok) {
    throw new Error(`Token exchange failed: ${resp.status}`);
  }
  const data = await resp.json();
  return data.access_token || '';
}

async function shopifyRequest(shop, token, method, path, body) {
  const resp = await fetch(`https://${shop}${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      'X-Shopify-Access-Token': token,
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Shopify API ${resp.status}: ${text}`);
  }
  return resp.json();
}

async function ensureScriptTag(shop) {
  const entry = shopStore.get(shop);
  if (!entry) return;
  const src = `${APP_URL}/loader.js?shop=${encodeURIComponent(shop)}`;
  await shopifyRequest(shop, entry.accessToken, 'POST', '/admin/api/2024-01/script_tags.json', {
    script_tag: {
      event: 'onload',
      src,
    },
  });
}

app.get('/', (req, res) => {
  res.send('APIShield Plus Shopify app skeleton. Visit /auth?shop=your-shop.myshopify.com');
});

app.get('/auth', (req, res) => {
  const shop = normalizeShop(req.query.shop);
  if (!shop || !SHOPIFY_API_KEY || !SHOPIFY_API_SECRET) {
    return res.status(400).send('Missing shop or API credentials.');
  }
  const state = crypto.randomBytes(16).toString('hex');
  pendingStates.set(state, shop);
  const redirectUri = `${APP_URL}/auth/callback`;
  const installUrl = `https://${shop}/admin/oauth/authorize?client_id=${encodeURIComponent(
    SHOPIFY_API_KEY
  )}&scope=${encodeURIComponent(SHOPIFY_SCOPES)}&redirect_uri=${encodeURIComponent(
    redirectUri
  )}&state=${encodeURIComponent(state)}`;
  res.redirect(installUrl);
});

app.get('/auth/callback', async (req, res) => {
  const shop = normalizeShop(req.query.shop);
  const code = req.query.code ? String(req.query.code) : '';
  const state = req.query.state ? String(req.query.state) : '';

  if (!shop || !code || !state || !pendingStates.has(state)) {
    return res.status(400).send('Invalid OAuth callback.');
  }
  if (!verifyHmac(req.query)) {
    return res.status(400).send('Invalid OAuth signature.');
  }

  try {
    const accessToken = await exchangeAccessToken(shop, code);
    shopStore.set(shop, {
      accessToken,
      config: {
        publicKey: '',
        apiBaseUrl: API_BASE_URL_DEFAULT,
        agentUrl: AGENT_URL_DEFAULT,
      },
    });
    await ensureScriptTag(shop);
    pendingStates.delete(state);
    res.redirect(`/settings?shop=${encodeURIComponent(shop)}`);
  } catch (err) {
    res.status(500).send(`OAuth failed: ${err.message}`);
  }
});

app.get('/settings', (req, res) => {
  const shop = normalizeShop(req.query.shop);
  const entry = shopStore.get(shop);
  if (!entry) {
    return res.status(401).send('Install the app first via /auth?shop=your-shop.myshopify.com');
  }
  const config = entry.config || {};
  res.send(`
    <html>
      <head><title>APIShield Plus Settings</title></head>
      <body>
        <h1>APIShield Plus Settings</h1>
        <form method="POST" action="/settings?shop=${encodeURIComponent(shop)}">
          <label>Public Key</label><br />
          <input name="publicKey" value="${config.publicKey || ''}" /><br /><br />
          <label>API Base URL</label><br />
          <input name="apiBaseUrl" value="${config.apiBaseUrl || ''}" /><br /><br />
          <label>Agent URL</label><br />
          <input name="agentUrl" value="${config.agentUrl || ''}" /><br /><br />
          <button type="submit">Save</button>
        </form>
        <p>Script tag is installed pointing at /loader.js for this shop.</p>
      </body>
    </html>
  `);
});

app.post('/settings', (req, res) => {
  const shop = normalizeShop(req.query.shop);
  const entry = shopStore.get(shop);
  if (!entry) {
    return res.status(401).send('Install the app first.');
  }
  const publicKey = req.body.publicKey ? String(req.body.publicKey).trim() : '';
  const apiBaseUrl = req.body.apiBaseUrl ? String(req.body.apiBaseUrl).trim() : '';
  const agentUrl = req.body.agentUrl ? String(req.body.agentUrl).trim() : '';

  entry.config = {
    publicKey,
    apiBaseUrl,
    agentUrl,
  };
  shopStore.set(shop, entry);
  res.redirect(`/settings?shop=${encodeURIComponent(shop)}`);
});

app.get('/loader.js', (req, res) => {
  const shop = normalizeShop(req.query.shop);
  const entry = shopStore.get(shop);
  res.type('application/javascript');
  if (!entry || !entry.config) {
    return res.send('console.warn("APIShield Plus not configured for this shop.");');
  }
  const config = entry.config;
  if (!config.publicKey || !config.agentUrl) {
    return res.send('console.warn("APIShield Plus missing public key or agent URL.");');
  }
  const ingestUrl = buildIngestUrl(config.apiBaseUrl);
  const publicKey = JSON.stringify(config.publicKey);
  const agentUrl = JSON.stringify(config.agentUrl);
  const ingestValue = JSON.stringify(ingestUrl || '/api/v1/ingest/browser');

  const js = `window.__API_SHIELD_KEY__ = ${publicKey};\n` +
    `window.__API_SHIELD_INGEST_URL__ = ${ingestValue};\n` +
    `(function(){var s=document.createElement('script');s.async=true;s.src=${agentUrl};document.head.appendChild(s);}());`;

  return res.send(js);
});

app.listen(PORT, () => {
  console.log(`APIShield Plus Shopify app listening on ${APP_URL}`);
});