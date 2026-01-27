# Generic Remediation Playbook

Use this template when there is no stack-specific playbook.

```json
{
  "version": 1,
  "sections": [
    {
      "title": "Triage and scope",
      "context": "Confirm what changed and define the blast radius before taking action.",
      "steps": [
        "Identify the first and last seen timestamps.",
        "List affected paths, environments, and user segments.",
        "Capture evidence: error rates, auth failures, and anomaly signals."
      ],
      "code_snippets": [],
      "verification_steps": [
        "Reproduce the issue in staging or a controlled environment if possible."
      ],
      "rollback_steps": [
        "Revert the last known deployment or configuration change."
      ],
      "risk_level": "medium"
    },
    {
      "title": "Containment and mitigation",
      "context": "Stop active abuse or breakage before attempting permanent fixes.",
      "steps": [
        "Enable temporary rate limits on affected routes.",
        "Block obvious abusive IP ranges if policy allows.",
        "Notify internal stakeholders about the ongoing incident."
      ],
      "code_snippets": [],
      "verification_steps": [
        "Confirm error rates and threat volumes drop within 10-15 minutes."
      ],
      "rollback_steps": [
        "Remove temporary blocks once the root cause is fixed."
      ],
      "risk_level": "low"
    },
    {
      "title": "Root cause remediation",
      "context": "Apply durable fixes based on the incident category.",
      "steps": [
        "Patch vulnerable dependencies or update configuration.",
        "Deploy hotfixes or roll back faulty releases.",
        "Add monitoring to catch regressions."
      ],
      "code_snippets": [],
      "verification_steps": [
        "Run regression checks on the affected flows.",
        "Verify stability across the next traffic peak."
      ],
      "rollback_steps": [
        "Revert the fix if errors increase or new issues appear."
      ],
      "risk_level": "medium"
    }
  ]
}
```
