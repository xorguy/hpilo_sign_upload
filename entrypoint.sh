#!/bin/bash
set -euo pipefail

echo "=== [Phase 1/2] Signing CSR with acme.sh (Cloudflare DNS) ==="
/root/.acme.sh/acme.sh --signcsr \
  --csr /csr/ilo.csr \
  --dns dns_cf \
  -d "${DOMAIN}" \
  --keylength 2048 \
  --dnssleep 5 \
  --accountemail "${ACME_EMAIL}"

SIGNED_CERT="/root/.acme.sh/${DOMAIN}/${DOMAIN}.cer"

if [ ! -f "${SIGNED_CERT}" ]; then
    echo "ERROR: Expected signed certificate not found at ${SIGNED_CERT}"
    exit 1
fi

echo "=== [Phase 2/2] Uploading signed certificate to iLO ==="
export CERT_PATH="${SIGNED_CERT}"
exec python /app/upload_cert.py
