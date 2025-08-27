#!/usr/bin/env bash
set -euo pipefail
BASE_URL="${BASE_URL:-http://localhost:8001}"  # use http for local dev; if port-forwarding TLS, set to https://localhost:8001 and add -k to curl
CURL="${CURL:-curl}"

post_fail() {
  user="$1"
  # Adjust to match your /events/auth schema: username + failed attempt
  $CURL -s -o /dev/null -w "%{http_code}\n" \
    -H 'Content-Type: application/json' \
    -X POST "$BASE_URL/events/auth" \
    --data "{\"user\":\"$user\",\"action\":\"login\",\"success\":false,\"source\":\"sim\"}"
}

echo "Simulating failed attempts for alice and ben..."
post_fail alice
post_fail alice
post_fail ben
post_fail ben
post_fail ben
echo "Done. Hit $BASE_URL/metrics and look for credential_stuffing_attempts_total."
