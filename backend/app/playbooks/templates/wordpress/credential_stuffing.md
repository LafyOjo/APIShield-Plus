# WordPress Credential Stuffing Playbook

```json
{
  "version": 1,
  "sections": [
    {
      "title": "Throttle login attempts",
      "context": "Reduce automated login retries and protect user accounts.",
      "steps": [
        "Enable a login rate limiter plugin or add WAF rules on /wp-login.php.",
        "Require CAPTCHA or step-up verification after repeated failures.",
        "Enable MFA for admin accounts."
      ],
      "code_snippets": [
        {
          "language": "bash",
          "snippet": "wp plugin install limit-login-attempts-reloaded --activate"
        }
      ],
      "verification_steps": [
        "Confirm repeated failed logins trigger rate limiting or CAPTCHA.",
        "Verify admin logins are protected by MFA."
      ],
      "rollback_steps": [
        "Disable the plugin or WAF rule if it blocks legitimate users."
      ],
      "risk_level": "high"
    },
    {
      "title": "Audit compromised accounts",
      "context": "Credential stuffing often succeeds on reused passwords.",
      "steps": [
        "Force password resets for impacted accounts.",
        "Review admin user list for unexpected accounts.",
        "Rotate credentials for any exposed admin users."
      ],
      "code_snippets": [],
      "verification_steps": [
        "Confirm admin list contains only approved accounts."
      ],
      "rollback_steps": [
        "Restore passwords or access after verifying legitimacy."
      ],
      "risk_level": "medium"
    }
  ]
}
```
