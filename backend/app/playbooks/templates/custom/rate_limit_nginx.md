# Rate Limit Login (Nginx)

```json
{
  "version": 1,
  "sections": [
    {
      "title": "Apply Nginx rate limits",
      "context": "Throttle login attempts to slow down automated abuse.",
      "steps": [
        "Add a limit_req_zone for login endpoints.",
        "Apply burst limits to balance real users and bots.",
        "Monitor auth success rates after deployment."
      ],
      "code_snippets": [
        {
          "language": "nginx",
          "snippet": "limit_req_zone $binary_remote_addr zone=login:10m rate=10r/m;\nserver {\n  location /login {\n    limit_req zone=login burst=20 nodelay;\n  }\n}"
        }
      ],
      "verification_steps": [
        "Confirm login throughput is stable and abuse volume drops."
      ],
      "rollback_steps": [
        "Remove limit_req directives if they block legitimate users."
      ],
      "risk_level": "medium"
    },
    {
      "title": "Add account protection",
      "context": "Reduce account takeover risk while the attack continues.",
      "steps": [
        "Enable MFA for high-risk accounts.",
        "Introduce CAPTCHA after repeated failures.",
        "Notify users with suspicious login attempts."
      ],
      "code_snippets": [],
      "verification_steps": [
        "Verify MFA enrollment and CAPTCHA triggers function correctly."
      ],
      "rollback_steps": [
        "Relax step-up authentication after the incident is resolved."
      ],
      "risk_level": "high"
    }
  ]
}
```
