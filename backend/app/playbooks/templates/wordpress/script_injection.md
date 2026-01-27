# WordPress Script Injection Response

```json
{
  "version": 1,
  "sections": [
    {
      "title": "Inspect WordPress assets",
      "context": "Plugins and themes are common injection points.",
      "steps": [
        "Review recently installed or updated plugins.",
        "Check theme files for unexpected script tags.",
        "Scan wp-content for modified files."
      ],
      "code_snippets": [],
      "verification_steps": [
        "Confirm the storefront HTML is free of injected scripts."
      ],
      "rollback_steps": [
        "Restore from the last known-good backup."
      ],
      "risk_level": "high"
    },
    {
      "title": "Harden WordPress",
      "context": "Reduce the chance of reinfection.",
      "steps": [
        "Update WordPress core, themes, and plugins.",
        "Disable unused plugins and admin accounts.",
        "Enable WAF rules for common CMS attacks."
      ],
      "code_snippets": [],
      "verification_steps": [
        "Monitor for new integrity alerts over the next 24 hours."
      ],
      "rollback_steps": [
        "Re-enable plugins one at a time if needed." 
      ],
      "risk_level": "medium"
    }
  ]
}
```
