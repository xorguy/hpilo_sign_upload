#!/usr/bin/env python3
"""
Download the current CSR from HP iLO 4.

iLO keeps the last CSR it generated on disk. This script retrieves it so the
entrypoint can sign and upload it without requiring a manually mounted file.

Required environment variables:
    ILO_HOST  — IP or hostname of the iLO management interface
    ILO_USER  — iLO username (must have config_ilo_priv)
    ILO_PASS  — iLO password

Usage: python download_csr.py <output_path>
"""
import os
import sys
import hpilo

ILO_HOST = os.environ.get('ILO_HOST')
ILO_USER = os.environ.get('ILO_USER', 'Administrator')
ILO_PASS = os.environ.get('ILO_PASS')


def validate_env():
    missing = [v for v in ('ILO_HOST', 'ILO_PASS') if not os.environ.get(v)]
    if missing:
        print(f"ERROR: Missing required environment variables: {', '.join(missing)}")
        sys.exit(1)


def main():
    if len(sys.argv) < 2:
        print("Usage: download_csr.py <output_path>")
        sys.exit(1)

    output_path = sys.argv[1]
    validate_env()

    print(f"Connecting to iLO at {ILO_HOST} to download CSR...")
    ilo = hpilo.Ilo(ILO_HOST, login=ILO_USER, password=ILO_PASS,
                    timeout=60, ssl_verify=False)

    try:
        csr = ilo.get_csr()
    except Exception as e:
        print(f"ERROR: Failed to retrieve CSR from iLO: {e}")
        print("       Make sure a CSR has been generated on the iLO first,")
        print("       or provide the CSR file manually via the CSR_DIR volume.")
        sys.exit(1)

    # python-hpilo may return the CSR as a string or wrapped in a dict
    if isinstance(csr, dict):
        csr_text = csr.get('csr') or csr.get('certificate_request') or ''
    else:
        csr_text = str(csr) if csr else ''

    if '-----BEGIN CERTIFICATE REQUEST-----' not in csr_text:
        print("ERROR: iLO did not return a valid PEM-encoded CSR.")
        print(f"       Raw response: {csr_text!r}")
        print("       Generate a CSR on the iLO web interface first.")
        sys.exit(1)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, 'w') as f:
        f.write(csr_text)

    print(f"CSR downloaded and saved to {output_path}")


if __name__ == '__main__':
    main()
