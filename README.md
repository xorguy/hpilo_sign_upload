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
    - [1. Generate the CSR on iLO](#1-generate-the-csr-on-ilo)
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

- **[acme.sh](https://github.com/acmesh-official/acme.sh)** handles the ACME DNS-01 challenge against Cloudflare to sign the CSR with a public CA — ZeroSSL by default, selectable via `CA_SERVER` (Let's Encrypt, Buypass, or any other CA acme.sh supports).
- **[download_csr.py](download_csr.py)** can fetch the current CSR directly from iLO if you do not provide one via a host mount.
- **[python-hpilo](https://github.com/seveas/python-hpilo)** uploads the signed certificate to iLO over its XML API.

No certificate authority credentials, private keys, or iLO passwords are ever baked into the image.

---

## How It Works

```
┌─────────────────────────────────────────────────────────────┐
│  Docker container                                           │
│                                                             │
│  Phase 0 ── entrypoint.sh                                  │
│    if /csr/ilo.csr exists:                                  │
│      └── use host-mounted CSR (read-only)                   │
│    else:                                                    │
│      └── download current CSR from iLO via XML API          │
│                                                             │
│  Phase 1 ── acme.sh --signcsr                              │
│      ├── reads CSR from /csr/ilo.csr or /tmp/ilo_*.csr     │
│      ├── creates TXT record in Cloudflare DNS               │
│      ├── waits for propagation                              │
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
├── entrypoint.sh           # Resolve CSR source, sign it, then upload the cert
├── download_csr.py         # Optional Phase 0: download the current CSR from iLO
├── upload_cert.py          # Phase 2: upload signed cert to iLO via python-hpilo
├── compose.yaml            # Docker Compose — build from source
├── compose.prebuilt.yaml   # Docker Compose — use pre-built ARM64 image from Docker Hub
├── requirements.txt        # Python dependencies (python-hpilo)
├── .env.example            # Template for iLO + optional CSR directory variables
├── .env.cf.example         # Template for Cloudflare + ACME variables
└── .gitignore              # Excludes .env, .env.cf, *.pem, *.key, *.csr
```

---

## Quick Start

### 1. Generate the CSR on iLO

1. Log in to the iLO web interface.
2. Navigate to **Administration → Security → SSL Certificate**.
3. Fill in the certificate subject fields (Common Name **must** match the hostname you use to reach iLO, e.g. `ilo.example.com`), **DO NOT CHECK** "include iLO IP Address(es)".
4. Click **Generate CSR** and wait a few minutes for the process to complete.
5. Do one of the following:
  - **Recommended with `compose.yaml`:** leave the CSR on iLO and let the container download it automatically.
  - **Manual / pre-built image flow:** return to the SSL Certificate page, click **Generate CSR**, and save the downloaded file as `ilo.csr` inside a host directory, for example `/srv/ilo/ilo.csr`.

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

The iLO host, user, password, and optional CSR directory are passed via `.env`. The simplest approach is:

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

For the default source-build flow in `compose.yaml`, you have two options:

**Option A: Let the container download the CSR from iLO**

- Set `ILO_HOST`, `ILO_USER`, and `ILO_PASS`.
- Leave `CSR_DIR` unset.
- Make sure a CSR has already been generated on the iLO.

Example:

```bash
export ILO_HOST=192.168.1.10
export ILO_USER=Administrator
export ILO_PASS=yourpassword
```

**Option B: Provide a host-mounted CSR directory**

- Save the CSR file as `ilo.csr` inside a host directory.
- Set `CSR_DIR` to that directory.

Example:

```bash
export ILO_HOST=192.168.1.10
export ILO_USER=Administrator
export ILO_PASS=yourpassword
export CSR_DIR=/srv/ilo
```

> **Pre-built ARM64 image note:** `compose.prebuilt.yaml` currently mounts a CSR file directly and still expects `CSR_PATH=/path/to/ilo.csr`.

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
=== [Phase 0/3] No CSR at /csr/ilo.csr — downloading from iLO ===
Connecting to iLO at 192.168.1.10 to download CSR...
CSR downloaded and saved to /tmp/ilo_downloaded.csr
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
| `CSR_DIR` | *(unset)* | Optional **host-side** directory containing `ilo.csr`. With `compose.yaml`, this directory is mounted read-only at `/csr`. If unset, the container downloads the CSR directly from iLO instead. |
| `CERT_PATH` | `/certs/signed_cert.pem` | Container-side path to the signed certificate. Set automatically by `entrypoint.sh`; override only if you are running `upload_cert.py` standalone. |
| `CA_SERVER` | `zerossl` | ACME CA to sign against. acme.sh shortnames: `letsencrypt`, `letsencrypt_test`, `buypass`, `buypass_test`, `google`, `googletest`, `sslcom` — or a full ACME directory URL for any other CA acme.sh supports. |
| `CA_EAB_KID` / `CA_EAB_HMAC_KEY` | *(unset)* | Optional External Account Binding credentials, required only by CAs that need them (e.g. `google`, `sslcom`). Leave both unset for `zerossl`/`letsencrypt`/`buypass`. |

> **Selecting a different CA:** set `CA_SERVER` in `.env` to one of the shortnames above (or a
> custom ACME directory URL). No other config changes are needed for CAs like Let's Encrypt or
> Buypass. CAs that require External Account Binding also need `CA_EAB_KID` and
> `CA_EAB_HMAC_KEY` set together — get these from the CA's own account dashboard.

For `compose.prebuilt.yaml`, use `CSR_PATH` instead:

| Variable | Default | Description |
| --- | --- | --- |
| `CSR_PATH` | *(required in `compose.prebuilt.yaml`)* | **Host-side** absolute path to the CSR file exported from iLO. Mounted read-only into the container at `/csr/ilo.csr`. |

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
- **CSR is mounted read-only** (`:ro`) when you provide `CSR_DIR` or `CSR_PATH` — the container cannot modify the source CSR file.
- **Automatic CSR download does not generate a CSR for you.** iLO must already have a current CSR available to retrieve.

---

## Troubleshooting

**`ERROR: Missing required environment variables: ILO_HOST, ILO_PASS`**
→ Ensure the variables are exported or present in `.env` / `compose.yaml`'s `environment` block.

**`ERROR: Failed to retrieve CSR from iLO: ...`**
→ No CSR is currently available to download from iLO, or the account lacks the required privilege. Generate the CSR in the iLO interface first, or provide `CSR_DIR` with a host-side `ilo.csr` file.

**`ERROR: iLO did not return a valid PEM-encoded CSR.`**
→ The CSR retrieval succeeded, but iLO did not return a usable PEM payload. Regenerate the CSR in iLO and retry.

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
