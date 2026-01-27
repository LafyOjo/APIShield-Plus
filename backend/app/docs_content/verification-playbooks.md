# Verification playbooks

Use these checks after applying a fix. The goal is to confirm recovery and document proof.

## Core checks

- **Threat volume drop**: failed logins or blocks decrease by at least 50%.
- **JS error reduction**: error rate drops and stays stable.
- **Conversion recovery**: checkout conversion rate returns to baseline.

## Time windows

- Compare the same time-of-day window before and after the fix.
- Use at least 60 minutes of data when possible.

## Evidence to capture

- TrustScore trend before vs after.
- Revenue leak estimate delta.
- Top factors that disappeared.

## When it is inconclusive

- Low traffic windows.
- Ongoing marketing or A/B tests.
- Still missing events or instrumentation.

## Recommended workflow

1. Apply presets.
2. Run verification.
3. Export the report for stakeholders.
