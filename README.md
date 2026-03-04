# hpilo_sign_upload

> **Automate trusted SSL certificates for HP iLO 4** — sign the iLO-generated CSR via the ACME DNS-01 challenge (Cloudflare) and upload the resulting certificate to the HP iLO 4 in a single `docker compose up`.

> [!NOTE]
> This project was co-authored with the assistance of AI. All code and documentation have been reviewed and tested by the author.

---

## Table of Contents

- [hpilo\_sign\_upload](#hpilo_sign_upload)
  - [Table of Contents](#table-of-contents)
  - [Overview](#overview)
  - [How It Works](#how-it-works)
  - [Prerequisites](#prerequisites)
  - [Project Structure](#project-structure)
  - [Quick Start](#quick-start)
    - [1. Export the CSR from iLO](#1-export-the-csr-from-ilo)
    - [2. Clone the repository](#2-clone-the-repository)
    - [3. Configure Cloudflare credentials](#3-configure-cloudflare-credentials)
    - [4. Configure iLO credentials](#4-configure-ilo-credentials)
    - [5. Run](#5-run)
  - [Configuration Reference](#configuration-reference)
    - [Cloudflare / ACME (`.env.cf`)](#cloudflare--acme-envcf)
    - [iLO \& runtime (`.env` / compose environment)](#ilo--runtime-env--compose-environment)
  - [Networking](#networking)
  - [Security Notes](#security-notes)
  - [Troubleshooting](#troubleshooting)
  - [License](#license)

---

## Overview

HP iLO 4 ships with a self-signed certificate, which causes browser warnings and breaks monitoring tools that enforce certificate validation. The correct way to replace it is to:

1. Let iLO **generate its own CSR** (so iLO keeps the private key — it is never exported).
2. Have that CSR signed by a trusted CA.
3. Upload **only the signed certificate** back to iLO.

This project automates steps 2 and 3 inside a Docker container:

- **[acme.sh](https://github.com/acmesh-official/acme.sh)** handles the ACME DNS-01 challenge against Cloudflare to sign the CSR with a public CA (ZeroSSL by default, Let's Encrypt also supported).
- **[python-hpilo](https://github.com/seveas/python-hpilo)** uploads the signed certificate to iLO over its XML API.

No certificate authority credentials, private keys, or iLO passwords are ever baked into the image.

---

## How It Works

```
┌─────────────────────────────────────────────────────────────┐
│  Docker container                                           │
│                                                             │
│  Phase 1 ── entrypoint.sh                                  │
│    acme.sh --signcsr                                        │
│      ├── reads  /csr/ilo.csr   (host-mounted, read-only)   │
│      ├── creates TXT record in Cloudflare DNS               │
│      ├── waits for propagation                             │
│      └── writes signed cert to /root/.acme.sh/<DOMAIN>/    │
│                                                             │
│  Phase 2 ── upload_cert.py                                 │
│    python-hpilo                                             │
│      ├── connects to iLO_HOST via XML API                   │
│      └── calls import_certificate(pem)                      │
└─────────────────────────────────────────────────────────────┘
                                │
                                ▼
                     iLO resets with new cert
                     (allow ~30–60 seconds)
```

---

## Prerequisites

| Requirement | Details |
|---|---|
| Docker + Docker Compose v2 | `docker compose` (plugin syntax) |
| HP iLO 4 | Firmware ≥ 2.x; must be reachable from the Docker host |
| iLO credentials | Account with **Configure iLO Settings** (`config_ilo_priv`) privilege |
| Cloudflare-managed DNS zone | The domain/subdomain in the iLO CSR must be in a zone you control via Cloudflare |
| Cloudflare API token | **Zone → DNS → Edit** permission scoped to the target zone |

> **iLO 4 key-length constraint:** iLO 4 only issues RSA 2048-bit CSRs. The `--keylength 2048` flag in `entrypoint.sh` is set accordingly and should not be changed.

---

## Project Structure

```
hpilo_sign_upload/
├── Dockerfile              # Python 3.12-slim + acme.sh + python-hpilo
├── entrypoint.sh           # Phase 1: sign CSR with acme.sh (Cloudflare DNS-01)
├── upload_cert.py          # Phase 2: upload signed cert to iLO via python-hpilo
├── compose.yaml            # Docker Compose — build from source
├── compose.prebuilt.yaml   # Docker Compose — use pre-built ARM64 image from Docker Hub
├── requirements.txt        # Python dependencies (python-hpilo)
├── .env.example            # Template for iLO + CSR path variables
├── .env.cf.example         # Template for Cloudflare + ACME variables
└── .gitignore              # Excludes .env, .env.cf, *.pem, *.key, *.csr
```

---

## Quick Start

### 1. Export the CSR from iLO

1. Log in to the iLO web interface.
2. Navigate to **Administration → Security → SSL Certificate**.
3. Fill in the certificate subject fields (Common Name **must** match the hostname you use to reach iLO, e.g. `ilo.example.com`), **DO NOT CHECK** "include iLO IP Address(es)".
4. Click **Generate CSR** and wait a few minutes for the process to complete.
5. Return to the SSL Certificate page, click **Generate CSR**, and copy the contents of the downloaded file (including `-----BEGIN CERTIFICATE REQUEST-----` and `-----END CERTIFICATE REQUEST-----`).
6. Save the file to a path on the Docker host, e.g. `/srv/ilo/ilo.csr`.

> **Important:** Do not generate a new CSR after this step. iLO regenerates the private key each time — if the private key changes, a previously signed certificate becomes invalid.

### 2. Clone the repository

```bash
git clone https://github.com/<your-username>/hpilo_sign_upload.git
cd hpilo_sign_upload
```

> **ARM64 / Raspberry Pi users:** A pre-built image is published on Docker Hub at [`xorguy/hpilo_sign_upload`](https://hub.docker.com/r/xorguy/hpilo_sign_upload). Skip the local build by using `compose.prebuilt.yaml` instead of `compose.yaml` (see [step 5](#5-run)).

### 3. Configure Cloudflare credentials

```bash
cp .env.cf.example .env.cf
chmod 600 .env.cf
$EDITOR .env.cf
```

Fill in the values (see [Configuration Reference](#cloudflare--acme-envcf) below).

### 4. Configure iLO credentials

The iLO host, user, password, and CSR path are passed via the `environment` block in `compose.yaml`. The simplest approach is to use a `.env` file:

```bash
cp .env.example .env
chmod 600 .env
$EDITOR .env
```

Then reference it in `compose.yaml` by adding it to `env_file`:

```yaml
env_file:
  - .env.cf
  - .env          # add this line
```

Or export the variables in your shell before running compose:

```bash
export ILO_HOST=192.168.1.10
export ILO_USER=Administrator
export ILO_PASS=yourpassword
export CSR_PATH=/srv/ilo/ilo.csr
```

### 5. Run

**Building from source** (all platforms):

```bash
docker compose up --build
```

**Using the pre-built ARM64 image** (no build required):

[![Docker Hub](https://img.shields.io/docker/pulls/xorguy/hpilo_sign_upload?logo=docker&label=Docker%20Hub)](https://hub.docker.com/r/xorguy/hpilo_sign_upload)

```bash
docker compose -f compose.prebuilt.yaml up
```

The pre-built image is available at [hub.docker.com/r/xorguy/hpilo_sign_upload](https://hub.docker.com/r/xorguy/hpilo_sign_upload) and targets `linux/arm64`.

Expected output:

```bash
=== [Phase 1/2] Signing CSR with acme.sh (Cloudflare DNS) ===
...
=== [Phase 2/2] Uploading signed certificate to iLO ===
[1/3] Connecting to iLO at 192.168.1.10...
[2/3] Uploading signed certificate...
[3/3] Certificate uploaded successfully.
      iLO is now resetting. Allow ~30-60 seconds before reconnecting.
```

After ~60 seconds, open the iLO web interface — the browser should trust the certificate.

---

## Configuration Reference

### Cloudflare / ACME (`.env.cf`)

| Variable | Description |
| --- | --- |
| `CF_Account_ID` | Your Cloudflare Account ID (dashboard → right sidebar) |
| `CF_Token` | Cloudflare API token with **Zone:DNS:Edit** permission |
| `CF_Zone_ID` | The Zone ID for the domain (dashboard → right sidebar) |
| `DOMAIN` | The fully-qualified domain name in the CSR, e.g. `ilo.example.com` |
| `ACME_EMAIL` | Email for ACME account registration (required by ZeroSSL) |

### iLO & runtime (`.env` / compose environment)

| Variable | Default | Description |
| --- | --- | --- |
| `ILO_HOST` | *(required)* | IP address or hostname of the iLO management interface |
| `ILO_USER` | `Administrator` | iLO username |
| `ILO_PASS` | *(required)* | iLO password |
| `CSR_PATH` | *(required)* | **Host-side** absolute path to the CSR file exported from iLO. Mounted read-only into the container at `/csr/ilo.csr`. |
| `CERT_PATH` | `/certs/signed_cert.pem` | Container-side path to the signed certificate. Set automatically by `entrypoint.sh`; override only if you are running `upload_cert.py` standalone. |

---

## Networking

By default `compose.yaml` uses `network_mode: bridge`. This works when the iLO management interface is reachable from the Docker host's default network.

If iLO lives on a dedicated management VLAN that requires the host's routing table, switch to host networking:

```yaml
# compose.yaml
services:
  ilo-cert-upload:
    network_mode: "host"
```

---

## Security Notes

- **Credentials are never baked into the image.** All secrets are injected at runtime via environment variables or `env_file`.
- **Keep `.env` and `.env.cf` out of version control.** The `.gitignore` already excludes them; verify with `git status` before pushing.
- **Cloudflare API token scope:** Create a scoped token with only `Zone:DNS:Edit` on the specific zone. Avoid using the global API key.
- **iLO SSL verification is disabled** (`ssl_verify=False` in `upload_cert.py`) because iLO's existing certificate is self-signed at upload time. This is intentional and limited to the upload connection only.
- **CSR is mounted read-only** (`:ro`) — the container cannot modify the source CSR file.

---

## Troubleshooting

**`ERROR: Missing required environment variables: ILO_HOST, ILO_PASS`**
→ Ensure the variables are exported or present in `.env` / `compose.yaml`'s `environment` block.

**`ERROR: Certificate file not found at /root/.acme.sh/<DOMAIN>/<DOMAIN>.cer`**
→ acme.sh failed to sign the CSR. Check that:
- `DOMAIN` in `.env.cf` matches the CN/SAN in the CSR exactly.
- The Cloudflare credentials are correct and the token has `Zone:DNS:Edit` permission.
- The DNS zone for `DOMAIN` is managed by the Cloudflare account you specified.

**`ERROR: iLO rejected the certificate`**
→ The signed certificate does not match iLO's current private key. This happens if a new CSR was generated in iLO after the signing step. Re-export the CSR from iLO and run again.

**iLO is unreachable after upload**
→ iLO automatically resets after a certificate import. Wait 60 seconds and retry.

**`dns_cf` hook errors / `CF_Token` not recognised**
→ Ensure the variable name is exactly `CF_Token` (mixed case), which is what the acme.sh Cloudflare hook expects.

---

## License

This project is licensed under the **GNU General Public License v3.0**. See [LICENSE](LICENSE) for the full text.
