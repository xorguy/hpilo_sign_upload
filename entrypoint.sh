#!/bin/bash
set -euo pipefail

CSR_MOUNTED="/csr/ilo.csr"
CSR_DOWNLOADED="/tmp/ilo_downloaded.csr"

# Use the mounted CSR if provided; otherwise download it from iLO.
if [ -f "${CSR_MOUNTED}" ]; then
    echo "=== Using provided CSR from ${CSR_MOUNTED} ==="
    CSR_PATH="${CSR_MOUNTED}"
else
    echo "=== [Phase 0/3] No CSR at ${CSR_MOUNTED} — downloading from iLO ==="
    python /app/download_csr.py "${CSR_DOWNLOADED}"
    CSR_PATH="${CSR_DOWNLOADED}"
fi

CA_SERVER="${CA_SERVER:-zerossl}"
CA_EAB_KID="${CA_EAB_KID:-}"
CA_EAB_HMAC_KEY="${CA_EAB_HMAC_KEY:-}"

echo "=== [Phase 1/2] Signing CSR with acme.sh (CA: ${CA_SERVER}, Cloudflare DNS) ==="
ACME_ARGS=(--signcsr \
  --csr "${CSR_PATH}" \
  --dns dns_cf \
  -d "${DOMAIN}" \
  --keylength 2048 \
  --dnssleep 5 \
  --accountemail "${ACME_EMAIL}" \
  --server "${CA_SERVER}")

if [ -n "${CA_EAB_KID}" ] && [ -n "${CA_EAB_HMAC_KEY}" ]; then
    ACME_ARGS+=(--eab-kid "${CA_EAB_KID}" --eab-hmac-key "${CA_EAB_HMAC_KEY}")
fi

/root/.acme.sh/acme.sh "${ACME_ARGS[@]}"

SIGNED_CERT="/root/.acme.sh/${DOMAIN}/${DOMAIN}.cer"

if [ ! -f "${SIGNED_CERT}" ]; then
    echo "ERROR: Expected signed certificate not found at ${SIGNED_CERT}"
    exit 1
fi

echo "=== [Phase 2/2] Uploading signed certificate to iLO ==="
export CERT_PATH="${SIGNED_CERT}"
exec python /app/upload_cert.py
