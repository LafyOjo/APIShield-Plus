# APIShield Plus Shopify App (v1)

This is a minimal Shopify app skeleton that installs a loader script into the
storefront and boots the APIShield browser agent.

## Quick start

1) Create a Shopify Partner app.

- App URL: `https://your-app.ngrok.io`
- Redirect URL: `https://your-app.ngrok.io/auth/callback`

2) Copy `.env.example` to `.env` and fill in:

- `SHOPIFY_API_KEY`
- `SHOPIFY_API_SECRET`
- `APP_URL`
- `API_BASE_URL`
- `AGENT_URL`

3) Install deps and start:

```
npm install
npm run dev
```

4) Install the app on a dev store:

```
https://your-app.ngrok.io/auth?shop=your-shop.myshopify.com
```

5) After OAuth, open the settings page and set your public key:

```
https://your-app.ngrok.io/settings?shop=your-shop.myshopify.com
```

The app installs a ScriptTag that loads `/loader.js`, which sets
`window.__API_SHIELD_KEY__` and `window.__API_SHIELD_INGEST_URL__`, then loads
`AGENT_URL`.

## Notes

- This skeleton stores tokens and settings in memory. Replace with a database
  before production.
- ScriptTag injection is the simplest v1 path. For a production app, consider a
  theme app extension (app embed) instead.

## Manual QA checklist

- App boots locally
- OAuth completes
- Loader script is injected (ScriptTag exists)
- Storefront requests `/loader.js` and the agent script