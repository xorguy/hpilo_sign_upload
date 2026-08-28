#!/bin/bash
set -euo pipefail

CSR_MOUNTED="/csr/ilo.csr"
CSR_DOWNLOADED="/tmp/ilo_downloaded.csr"

# Use the mounted CSR if provided; otherwise ask iLO for one (generating a
# new CSR/key on iLO itself if it doesn't have one yet).
if [ -f "${CSR_MOUNTED}" ]; then
    echo "=== Using provided CSR from ${CSR_MOUNTED} ==="
    CSR_PATH="${CSR_MOUNTED}"
else
    echo "=== [Phase 0/3] No CSR at ${CSR_MOUNTED} — checking iLO (will generate one for CN=${DOMAIN} if none exists) ==="
    python /app/download_csr.py "${CSR_DOWNLOADED}"
    CSR_PATH="${CSR_DOWNLOADED}"
fi

echo "=== [Phase 1/2] Signing CSR with acme.sh (Cloudflare DNS) ==="
/root/.acme.sh/acme.sh --signcsr \
  --csr "${CSR_PATH}" \
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
