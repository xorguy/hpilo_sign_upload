#!/usr/bin/env python3
"""
Upload a pre-signed SSL certificate to HP iLO 4.

Required environment variables:
    ILO_HOST  — IP or hostname of the iLO management interface
    ILO_USER  — iLO username (must have config_ilo_priv)
    ILO_PASS  — iLO password

Required volume mount:
    /certs/signed_cert.pem  — The signed certificate in PEM format

The certificate MUST have been signed from the CSR that iLO itself generated.
"""
import os
import sys
import hpilo

CERT_PATH = os.environ.get('CERT_PATH', '/certs/signed_cert.pem')
ILO_HOST  = os.environ.get('ILO_HOST')
ILO_USER  = os.environ.get('ILO_USER', 'Administrator')
ILO_PASS  = os.environ.get('ILO_PASS')


def validate_env():
    missing = [v for v in ('ILO_HOST', 'ILO_PASS') if not os.environ.get(v)]
    if missing:
        print(f"ERROR: Missing required environment variables: {', '.join(missing)}")
        sys.exit(1)


def read_cert(path):
    if not os.path.isfile(path):
        print(f"ERROR: Certificate file not found at {path}")
        sys.exit(1)
    with open(path, 'r') as f:
        cert = f.read()
    if '-----BEGIN CERTIFICATE-----' not in cert:
        print("ERROR: File does not appear to be a PEM-encoded certificate.")
        sys.exit(1)
    return cert


def main():
    validate_env()
    cert_pem = read_cert(CERT_PATH)

    print(f"[1/3] Connecting to iLO at {ILO_HOST}...")
    ilo = hpilo.Ilo(ILO_HOST, login=ILO_USER, password=ILO_PASS,
                    timeout=60, ssl_verify=False)

    # print("[2/4] Current certificate subject info:")
    # try:
    #     info = ilo.get_cert_subject_info()
    #     for key, val in info.items():
    #         print(f"      {key}: {val}")
    # except Exception as e:
    #     print(f"      (Could not retrieve cert info: {e})")

    print("[2/3] Uploading signed certificate...")
    try:
        ilo.import_certificate(cert_pem)
    except hpilo.IloError as e:
        print(f"ERROR: iLO rejected the certificate: {e}")
        print("       Verify the cert was signed from the CSR iLO generated.")
        sys.exit(1)

    print("[3/3] Certificate uploaded successfully.")
    print("      iLO is now resetting. Allow ~30-60 seconds before reconnecting.")


if __name__ == '__main__':
    main()
