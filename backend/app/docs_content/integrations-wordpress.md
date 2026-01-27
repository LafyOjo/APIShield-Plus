# WordPress integration

WordPress sites can install the APIShield snippet safely without editing core files.

## Recommended approach

1. Use a header injection plugin (for example: "Insert Headers and Footers").
2. Paste the APIShield snippet into the **Header** section.
3. Save and reload your site.

## Verify events

- Visit your homepage and a logged-in page.
- Confirm events are present in **Security Events**.

## Notes

- Avoid placing the snippet in a theme file that will be overwritten by updates.
- If you have caching enabled, purge caches after adding the script.
