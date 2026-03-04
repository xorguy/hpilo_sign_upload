FROM python:3.12-slim

# curl, git and openssl are required by acme.sh
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        git \
        openssl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install python-hpilo
RUN pip install --no-cache-dir python-hpilo==4.4.3

# Install acme.sh via git clone so the path is guaranteed and the build
# never fails silently. --home pins the install to /root/.acme.sh.
# dns_cf (Cloudflare DNS API) is bundled inside acme.sh — no extra step needed.
RUN git clone --depth=1 https://github.com/acmesh-official/acme.sh.git /tmp/acme.sh \
    && cd /tmp/acme.sh && ./acme.sh --install --no-cron --home /root/.acme.sh \
    && rm -rf /tmp/acme.sh

# Copy scripts
COPY upload_cert.py /app/upload_cert.py
COPY entrypoint.sh  /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# /csr : host-mounted CSR file (read-only at runtime)
VOLUME ["/csr"]

ENTRYPOINT ["/app/entrypoint.sh"]
