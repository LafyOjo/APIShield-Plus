# Brute Force Login Response (Generic)

```json
{
  "version": 1,
  "sections": [
    {
      "title": "Assess brute force activity",
      "context": "Confirm repeated attempts against a small set of accounts.",
      "steps": [
        "Review failed logins per user over short time windows.",
        "Identify IPs or ASNs driving the volume.",
        "Check for repeated attempts on privileged accounts."
      ],
      "code_snippets": [],
      "verification_steps": [
        "Ensure the spike is not caused by a deployment or auth outage."
      ],
      "rollback_steps": [
        "Roll back temporary blocks if they impact legitimate users."
      ],
      "risk_level": "high"
    },
    {
      "title": "Containment",
      "context": "Slow attackers and protect critical accounts.",
      "steps": [
        "Apply IP-based throttling and lockouts.",
        "Enable adaptive MFA for affected users.",
        "Increase logging on auth endpoints for forensic review."
      ],
      "code_snippets": [],
      "verification_steps": [
        "Confirm rate limits are reducing attempts within minutes."
      ],
      "rollback_steps": [
        "Remove lockouts after the threat subsides."
      ],
      "risk_level": "medium"
    }
  ]
}
```
