"""
Generate a self-signed certificate matching the New World game server certificate.

The real server cert has:
    CN=New World, O=Amazon, OU=Amazon Game Studios, Email=ags-nw@amazon.com
    Location: SNA11, California, US
    Validity: 2025-08-04 to 2027-01-06
    Signature: RSA 2048-bit, SHA-256

Usage:
    python generate_cert.py [--out-dir server/certs]
"""

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUT = PROJECT_DIR / "server" / "certs"


def generate(out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)

    key_path = out_dir / "server.key"
    cert_path = out_dir / "server.crt"

    # Subject matching the real New World server certificate
    subject = (
        "/C=US"
        "/ST=California"
        "/L=SNA11"
        "/O=Amazon"
        "/OU=Amazon Game Studios"
        "/CN=New World"
        "/emailAddress=ags-nw@amazon.com"
    )

    cmd = [
        "openssl", "req",
        "-x509",
        "-newkey", "rsa:2048",
        "-keyout", str(key_path),
        "-out", str(cert_path),
        "-days", "730",
        "-nodes",           # no passphrase
        "-sha256",
        "-subj", subject,
    ]

    print(f"[*] Generating certificate...")
    print(f"    Key:  {key_path}")
    print(f"    Cert: {cert_path}")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[!] openssl failed:\n{result.stderr}")
        sys.exit(1)

    print(f"[+] Certificate generated successfully")

    # Verify
    verify = subprocess.run(
        ["openssl", "x509", "-in", str(cert_path), "-text", "-noout"],
        capture_output=True, text=True,
    )
    print(f"\n{verify.stdout}")

    return key_path, cert_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate New World server certificate")
    parser.add_argument("--out-dir", type=str, default=str(DEFAULT_OUT))
    args = parser.parse_args()
    generate(Path(args.out_dir))
