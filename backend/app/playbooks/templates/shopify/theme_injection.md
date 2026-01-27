# Shopify Theme Injection Response

```json
{
  "version": 1,
  "sections": [
    {
      "title": "Inspect theme changes",
      "context": "Shopify theme edits are a common injection vector.",
      "steps": [
        "Review recent theme edits in Shopify admin.",
        "Check theme.liquid for unexpected script tags.",
        "Disable recently added apps that inject scripts."
      ],
      "code_snippets": [],
      "verification_steps": [
        "Confirm the injected script is removed from the storefront HTML."
      ],
      "rollback_steps": [
        "Restore the last known-good theme version."
      ],
      "risk_level": "high"
    },
    {
      "title": "Harden storefront",
      "context": "Reduce exposure after cleanup.",
      "steps": [
        "Limit app permissions to only required scopes.",
        "Enable Shopify security settings and two-factor auth for admins.",
        "Consider adding a CSP via Shopify admin if supported." 
      ],
      "code_snippets": [],
      "verification_steps": [
        "Verify storefront rendering and checkout flows work as expected."
      ],
      "rollback_steps": [
        "Remove CSP or app restrictions if they break critical features."
      ],
      "risk_level": "medium"
    }
  ]
}
```
