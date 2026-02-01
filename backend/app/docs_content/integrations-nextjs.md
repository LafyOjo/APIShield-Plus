# Next.js integration

Use the middleware hook to enrich security telemetry and ensure requests are correlated.

## Steps

- Install the SDK: `npm install @apishield/next`
- Add the middleware file in your project root.
- Replace `YOUR_PUBLIC_KEY` with the environment key from APIShield+.

```ts
// middleware.ts
import { apiShieldMiddleware } from "@apishield/next";

export default apiShieldMiddleware({
  publicKey: "YOUR_PUBLIC_KEY",
});
```

## Verify

- Navigate to your site and confirm events appear in the Security Map.
- Check `/api/v1/ingest/browser` responses are 200.
