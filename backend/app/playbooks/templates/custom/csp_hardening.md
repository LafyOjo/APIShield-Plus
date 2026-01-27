# CSP Hardening (Generic)

```json
{
  "version": 1,
  "sections": [
    {
      "title": "Audit CSP violations",
      "context": "Identify which sources are blocked and why.",
      "steps": [
        "Review CSP reports for blocked script or style sources.",
        "Confirm whether violations are legitimate or malicious.",
        "Baseline the current CSP policy in production."
      ],
      "code_snippets": [],
      "verification_steps": [
        "Validate the CSP report endpoint is receiving events."
      ],
      "rollback_steps": [
        "Disable new CSP rules if critical assets are blocked."
      ],
      "risk_level": "medium"
    },
    {
      "title": "Apply stricter CSP",
      "context": "Reduce the attack surface for script injection.",
      "steps": [
        "Move inline scripts to external files where possible.",
        "Add nonces or hashes for any remaining inline scripts.",
        "Restrict script-src to known CDNs and self." 
      ],
      "code_snippets": [
        {
          "language": "nginx",
          "snippet": "add_header Content-Security-Policy \"default-src 'self'; script-src 'self' https://cdn.example.com; object-src 'none'; base-uri 'self'; frame-ancestors 'none'\" always;"
        }
      ],
      "verification_steps": [
        "Ensure critical pages load without CSP errors.",
        "Monitor CSP reports for new violations."
      ],
      "rollback_steps": [
        "Rollback the policy if essential scripts are blocked."
      ],
      "risk_level": "high"
    }
  ]
}
```
