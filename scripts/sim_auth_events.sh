#!/usr/bin/env bash
set -euo pipefail
BASE_URL="${BASE_URL:-http://localhost:8001}"   # use https://localhost:8001 with -k if your dev server has TLS
CURL_FLAGS=${CURL_FLAGS:-}

post() {
  user="$1"; success="$2"; stuff="$3"; blocked="$4"; rule="${5:-}"
  curl -s $CURL_FLAGS -H 'content-type: application/json' -X POST "$BASE_URL/events/auth" \
    --data "{\"username\":\"$user\",\"success\":$success,\"is_credential_stuffing\":$stuff,\"blocked\":$blocked,\"block_rule\":\"$rule\"}" >/dev/null
}

echo "Seeding events for alice and ben..."
post alice false true  true  rate-limit
post alice false true  false ""
post ben   false true  true  ip-reputation
post ben   false false false ""
post alice true  false false ""
echo "Done."
