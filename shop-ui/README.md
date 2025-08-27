# Demo Shop UI

This directory contains a very simple HTML/JavaScript front-end for the Node.js demo shop.

Open `index.html` in your browser after starting the shop server with:

```bash
cd demo-shop
npm install
node server.js
```

The UI communicates with the API on `http://localhost:3005`. You can browse products, register and log in, add items to your cart, and simulate a purchase. When the backend enforces per-request re-authentication, protected actions prompt for your password and send it in the `X-Reauth-Password` header. If you cancel or enter it incorrectly, the UI logs you out so the login button becomes available again.

FORWARD_API=true
API_BASE=http://127.0.0.1:8001
API_KEY=demo-key
API_TIMEOUT_MS=5000
