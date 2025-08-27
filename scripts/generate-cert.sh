#!/usr/bin/env bash
set -euo pipefail

# ---- Configurable bits (override via env) ----
CN="${CN:-detector}"
ORG="${ORG:-demo}"
NAMESPACE="${NAMESPACE:-demo}"
SECRET_NAME="${SECRET_NAME:-detector-tls}"
ALT_DNS_CSV="${ALT_DNS:-detector,localhost}"     # comma-separated
ALT_IPS_CSV="${ALT_IPS:-127.0.0.1}"               # comma-separated
DAYS="${DAYS:-365}"

# ---- Prep scratch space and cleanup ----
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

KEY="$TMPDIR/server.key"
CRT="$TMPDIR/server.crt"
CNF="$TMPDIR/openssl.cnf"

# ---- Build an OpenSSL config (avoids Git Bash path mangling) ----
# Convert CSV -> numbered SAN entries
i=1; ALT_DNS_LINES=""
IFS=',' read -ra DNS_ARR <<< "$ALT_DNS_CSV"
for d in "${DNS_ARR[@]}"; do ALT_DNS_LINES+="DNS.$i = ${d}\n"; ((i++)); done

i=1; ALT_IP_LINES=""
IFS=',' read -ra IP_ARR <<< "$ALT_IPS_CSV"
for ip in "${IP_ARR[@]}"; do ALT_IP_LINES+="IP.$i = ${ip}\n"; ((i++)); done

cat > "$CNF" <<EOF
[ req ]
prompt = no
distinguished_name = dn
x509_extensions = v3_req

[ dn ]
CN = ${CN}
O  = ${ORG}

[ v3_req ]
subjectAltName = @alt_names

[ alt_names ]
$(printf "%b" "$ALT_DNS_LINES")
$(printf "%b" "$ALT_IP_LINES")
EOF

# ---- Generate key + self-signed cert (with SANs) ----
# Using a config file avoids the /CN=... subject string entirely.
openssl req -x509 -nodes -newkey rsa:2048 \
  -days "$DAYS" \
  -keyout "$KEY" \
  -out "$CRT" \
  -config "$CNF" \
  -extensions v3_req

echo "Created $CRT and $KEY (CN=${CN}, O=${ORG}, SANs: DNS=${ALT_DNS_CSV}; IP=${ALT_IPS_CSV})"

# ---- Create/Update the Kubernetes TLS secret idempotently ----
# (If it exists, this will update it. If not, it will create it.)
kubectl -n "$NAMESPACE" create secret tls "$SECRET_NAME" \
  --key "$KEY" --cert "$CRT" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "Ensured TLS secret '$SECRET_NAME' in namespace '$NAMESPACE'"

# ---- (Optional) Dump a brief cert summary ----
openssl x509 -in "$CRT" -noout -subject -issuer -dates -ext subjectAltName || true