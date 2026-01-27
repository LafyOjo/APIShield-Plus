# Troubleshooting: no events showing

If your dashboards are empty, follow this checklist.

## Checklist

- **Is the snippet installed?** Confirm it is present in your HTML `<head>`.
- **Is the public key correct?** Use the key from the selected environment.
- **Are you blocking scripts?** Temporarily disable ad blockers.
- **Is your site HTTPS?** Mixed content can block script loading.
- **Is the site cached?** Purge CDN or WordPress caches after installing.

## Verify with browser tools

1. Open DevTools → Network.
2. Filter for `agent.js`.
3. Confirm a 200 status and no CSP errors.

## If still stuck

- Try a new key and re-deploy the snippet.
- Contact support with the website domain and environment name.
