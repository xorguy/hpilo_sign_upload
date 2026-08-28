#!/usr/bin/env python3
"""
Obtain a CSR from HP iLO 4 — download the one already there, or ask iLO to
generate one first if it has none.

iLO exposes a single RIBCL call for this: certificate_signing_request().
Called with no arguments it returns whatever CSR iLO currently has (if any).
Called with common_name=<FQDN> it triggers generation of a NEW CSR (and a new
private key) for that CN. Because regenerating invalidates any certificate
already signed against the old CSR/key, generation is only ever triggered as
a fallback: we always probe with no arguments first, and only ask iLO to
generate a CSR when that probe makes clear none exists yet.

Required environment variables:
    ILO_HOST  — IP or hostname of the iLO management interface
    ILO_USER  — iLO username (must have config_ilo_priv)
    ILO_PASS  — iLO password
    DOMAIN    — FQDN to use as the CSR's Common Name if iLO has no CSR yet

Usage: python download_csr.py <output_path>
"""
import os
import subprocess
import sys
import time

import hpilo

ILO_HOST = os.environ.get('ILO_HOST')
ILO_USER = os.environ.get('ILO_USER', 'Administrator')
ILO_PASS = os.environ.get('ILO_PASS')
DOMAIN = os.environ.get('DOMAIN')

GENERATE_TIMEOUT = 900   # seconds — HP's own error message says "10 minutes or more"
GENERATE_INTERVAL = 20   # seconds between polls


def validate_env():
    missing = [v for v in ('ILO_HOST', 'ILO_PASS', 'DOMAIN') if not os.environ.get(v)]
    if missing:
        print(f"ERROR: Missing required environment variables: {', '.join(missing)}")
        if 'DOMAIN' in missing:
            print("       DOMAIN is required even for the auto-download path — it is")
            print("       used as the CSR's Common Name if iLO has no CSR yet.")
        sys.exit(1)


def extract_csr_text(csr):
    """certificate_signing_request() returns a plain string; handle a dict
    defensively in case a future python-hpilo version wraps it."""
    if isinstance(csr, dict):
        return csr.get('csr') or csr.get('certificate_request') or ''
    return str(csr) if csr else ''


def warn_if_cn_mismatch(csr_text):
    """Best-effort CN check using the openssl CLI (already in the image for
    acme.sh). Never fatal — just a heads-up before Phase 1 fails loudly."""
    try:
        result = subprocess.run(
            ['openssl', 'req', '-noout', '-subject', '-nameopt', 'multiline'],
            input=csr_text, capture_output=True, text=True, timeout=10,
        )
        cn_line = next((l for l in result.stdout.splitlines() if 'commonName' in l), '')
        cn = cn_line.split('=', 1)[1].strip() if '=' in cn_line else ''
        if cn and cn != DOMAIN:
            print(f"WARNING: CSR Common Name ({cn!r}) does not match DOMAIN ({DOMAIN!r}).")
            print("         Not regenerating — iLO issues a new private key on every")
            print("         CSR generation, which would invalidate any cert already")
            print("         signed against the current one. Using the existing CSR")
            print("         as-is; acme.sh will fail at signing time if this is wrong.")
    except Exception:
        pass  # best-effort only — never block the pipeline over this check


def wait_for_csr(ilo, trigger_common_name):
    """Poll certificate_signing_request() until it returns a CSR or the
    timeout expires. trigger_common_name is passed only on the first call
    (the call that actually requests generation); subsequent polls call with
    no arguments to just check status, never re-triggering generation."""
    deadline = time.time() + GENERATE_TIMEOUT
    common_name = trigger_common_name
    while time.time() < deadline:
        try:
            csr = ilo.certificate_signing_request(common_name=common_name) if common_name \
                else ilo.certificate_signing_request()
            csr_text = extract_csr_text(csr)
            if '-----BEGIN CERTIFICATE REQUEST-----' in csr_text:
                return csr_text
        except hpilo.IloGeneratingCSR:
            pass  # still working — keep polling
        except hpilo.IloError as e:
            print(f"ERROR: iLO rejected the CSR request: {e}")
            sys.exit(1)
        common_name = None  # only pass it on the triggering call
        print(f"  still generating, retrying in {GENERATE_INTERVAL}s...")
        time.sleep(GENERATE_INTERVAL)
    print(f"ERROR: Timed out after {GENERATE_TIMEOUT}s waiting for iLO to generate a CSR.")
    sys.exit(1)


def try_fetch_existing_csr(ilo):
    """Probe iLO with no arguments. Never passes common_name here, so this
    can only ever return what iLO already has — it must not itself trigger
    generation of a new CSR/private key."""
    try:
        csr = ilo.certificate_signing_request()
        csr_text = extract_csr_text(csr)
        return csr_text if '-----BEGIN CERTIFICATE REQUEST-----' in csr_text else None
    except hpilo.IloGeneratingCSR:
        # A generation was already in progress (e.g. triggered manually, or by
        # a previous run of this script that got interrupted) — wait for that
        # one to finish rather than starting a second one.
        print("iLO is already generating a CSR — waiting for it to finish...")
        return wait_for_csr(ilo, trigger_common_name=None)
    except hpilo.IloError as e:
        print(f"No usable CSR currently on iLO ({e}) — will request a new one.")
        return None


def main():
    if len(sys.argv) < 2:
        print("Usage: download_csr.py <output_path>")
        sys.exit(1)

    output_path = sys.argv[1]
    validate_env()

    print(f"Connecting to iLO at {ILO_HOST} to check for an existing CSR...")
    ilo = hpilo.Ilo(ILO_HOST, login=ILO_USER, password=ILO_PASS,
                    timeout=60, ssl_verify=False)

    csr_text = try_fetch_existing_csr(ilo)

    if csr_text:
        print("Found a CSR on iLO.")
        warn_if_cn_mismatch(csr_text)
    else:
        print(f"No CSR present on iLO — requesting a new one for CN={DOMAIN}...")
        print("This mints a new iLO private key and can take several minutes.")
        csr_text = wait_for_csr(ilo, trigger_common_name=DOMAIN)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, 'w') as f:
        f.write(csr_text)

    print(f"CSR saved to {output_path}")


if __name__ == '__main__':
    main()
