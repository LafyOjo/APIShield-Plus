# TrustScore and Revenue Leak estimates

These models explain "what is wrong" and "what it costs".

## TrustScore (0-100)

- **100** means healthy, stable traffic.
- **0** means high risk and likely breakage.
- The score is driven by signals: login failures, integrity issues, JS errors, and anomalies.

## Risk factors

Each score includes a list of factors with evidence, such as:

- `credential_stuffing_detected`
- `csp_violation_spike`
- `js_error_spike`

## Revenue Leak estimates

Revenue leaks estimate lost conversions per page:

- Compare **baseline conversion rate** to observed rate.
- Multiply by sessions and revenue per conversion.
- Adjust confidence using TrustScore overlap.

## How to use this

- Focus on pages with **low trust** and **high leak**.
- Open remediation playbooks for stack-specific fixes.
