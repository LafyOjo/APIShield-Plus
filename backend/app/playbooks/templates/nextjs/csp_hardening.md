# Next.js CSP Hardening

```json
{
  "version": 1,
  "sections": [
    {
      "title": "Review CSP violations",
      "context": "Identify missing hosts and inline script usage in Next.js pages.",
      "steps": [
        "Collect CSP reports for the affected routes.",
        "Identify scripts that require nonces or hashes.",
        "Update Next.js headers configuration."
      ],
      "code_snippets": [
        {
          "language": "javascript",
          "snippet": "const securityHeaders = [\n  { key: 'Content-Security-Policy', value: \"default-src 'self'; script-src 'self' https://cdn.example.com; object-src 'none'; base-uri 'self'; frame-ancestors 'none'\" }\n];\n\nmodule.exports = {\n  async headers() {\n    return [\n      { source: '/(.*)', headers: securityHeaders }\n    ];\n  }\n};"
        }
      ],
      "verification_steps": [
        "Confirm CSP headers are present on all pages.",
        "Ensure no critical scripts are blocked."
      ],
      "rollback_steps": [
        "Revert the header change if it blocks required scripts."
      ],
      "risk_level": "medium"
    }
  ]
}
```
