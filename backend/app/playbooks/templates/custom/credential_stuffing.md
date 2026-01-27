# Credential Stuffing Response (Generic)

```json
{
  "version": 1,
  "sections": [
    {
      "title": "Confirm credential stuffing pattern",
      "context": "Validate that the spikes are tied to password reuse attempts.",
      "steps": [
        "Check login failure rates by IP and user agent.",
        "Look for high-volume attempts across many usernames.",
        "Correlate with known breach lists if available."
      ],
      "code_snippets": [],
      "verification_steps": [
        "Ensure the spike aligns with abnormal login failures." 
      ],
      "rollback_steps": [
        "Remove temporary protections once a permanent mitigation is deployed."
      ],
      "risk_level": "high"
    },
    {
      "title": "Add friction and rate limits",
      "context": "Slow down automated attempts while keeping real users flowing.",
      "steps": [
        "Enable per-IP rate limits on /login and /auth endpoints.",
        "Require CAPTCHA or step-up verification after N failures.",
        "Throttle requests from datacenter ASNs if policy allows."
      ],
      "code_snippets": [],
      "verification_steps": [
        "Login failures should stabilize without blocking real customers."
      ],
      "rollback_steps": [
        "Relax limits gradually if false positives rise."
      ],
      "risk_level": "medium"
    },
    {
      "title": "Protect accounts",
      "context": "Reduce account takeover risk immediately.",
      "steps": [
        "Force password resets for affected users.",
        "Enable MFA for high-risk accounts.",
        "Notify customers about suspicious activity."
      ],
      "code_snippets": [],
      "verification_steps": [
        "Verify account lockouts and password reset flows are functional."
      ],
      "rollback_steps": [
        "Revert any overly strict lockouts after verification."
      ],
      "risk_level": "high"
    }
  ]
}
```
