# Shopify integration

Shopify supports custom script injection through your theme.

## Recommended approach

1. Go to **Online Store** → **Themes** → **Edit code**.
2. Open `theme.liquid`.
3. Paste the APIShield snippet before `</head>`.
4. Save and reload your storefront.

## Verify events

- Open a product page and click "Add to cart".
- Confirm events show up in **Security Events**.

## Notes

- If you use a theme editor app, ensure it does not remove custom scripts.
- For staging, use a separate environment and key.
