# Script Injection Response (Generic)

```json
{
  "version": 1,
  "sections": [
    {
      "title": "Identify injected scripts",
      "context": "Locate the source of unexpected scripts or tags.",
      "steps": [
        "Diff recent deploys or CMS/theme edits.",
        "Scan for unknown script tags in critical templates.",
        "Check third-party tags and tag managers for changes."
      ],
      "code_snippets": [],
      "verification_steps": [
        "Confirm injected scripts are present in production HTML."
      ],
      "rollback_steps": [
        "Revert the last template or tag-manager change."
      ],
      "risk_level": "high"
    },
    {
      "title": "Remove and harden",
      "context": "Clean the injection vector and reduce future risk.",
      "steps": [
        "Remove malicious or unknown scripts.",
        "Rotate secrets if they may have been exposed.",
        "Harden CSP and lock down admin/editor access."
      ],
      "code_snippets": [],
      "verification_steps": [
        "Verify critical paths no longer load the injected scripts."
      ],
      "rollback_steps": [
        "If removal breaks functionality, restore known-good scripts only."
      ],
      "risk_level": "high"
    }
  ]
}
```
