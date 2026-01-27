# Checkout Conversion Drop + JS Errors (Generic)

```json
{
  "version": 1,
  "sections": [
    {
      "title": "Confirm error-driven drop-offs",
      "context": "Correlate JS errors with conversion drops on key paths.",
      "steps": [
        "Review JS error counts for /checkout and /cart.",
        "Compare conversion rates before and after the spike.",
        "Identify recent releases or tag changes."
      ],
      "code_snippets": [],
      "verification_steps": [
        "Validate reproduction in a staging environment."
      ],
      "rollback_steps": [
        "Rollback the most recent frontend deployment."
      ],
      "risk_level": "medium"
    },
    {
      "title": "Mitigate and verify",
      "context": "Restore checkout flow stability quickly.",
      "steps": [
        "Patch or disable the failing script.",
        "Add client-side error logging around checkout flows.",
        "Retest the checkout end-to-end."
      ],
      "code_snippets": [],
      "verification_steps": [
        "Confirm error rates and conversion recover within the next hour."
      ],
      "rollback_steps": [
        "Revert patches if they introduce new errors."
      ],
      "risk_level": "medium"
    }
  ]
}
```
