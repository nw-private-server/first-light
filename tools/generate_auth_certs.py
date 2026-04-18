r"""
Generate a self-signed root CA + an auth-mock cert with SAN entries
covering every hostname the game client contacts during auth.

Outputs into server/certs/:
  newworld_ca.crt / newworld_ca.key    - the root CA
  auth.crt / auth.key                  - the server cert signed by the CA

Next steps after running this:
  1. Trust the CA in Windows:
       certutil -addstore -f "ROOT" server\certs\newworld_ca.crt
  2. Redirect hostnames via hosts file (see tools/setup_hosts.py).
  3. Run: python -m server.auth_mock --port 443
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
CERTS_DIR = PROJECT_DIR / "server" / "certs"

# Every hostname the game hits during auth + remote-config fetch.
# Keep this list in sync with server/auth_mock.py's ROUTES table.
AUTH_HOSTS = [
    # Channel service
    "d2c74t4zimux3r.cloudfront.net",

    # HTTP gateway CloudFront distributions (all 5 regions)
    "d1w0bfy6smo4d1.cloudfront.net",   # eu-central-1
    "d1cjlmzk0xrm0z.cloudfront.net",   # sa-east-1
    "d2oeuvxi3kfsrw.cloudfront.net",   # us-east-1
    "d3bj4csovi1fe8.cloudfront.net",   # us-west-2
    "de4mfzk9wkelz.cloudfront.net",    # ap-southeast-2

    # Auth-stack API Gateway (all us-east-1 regardless of game region)
    "2mfrik7h83.execute-api.us-east-1.amazonaws.com",
    "kqqt5twsi7.execute-api.us-east-1.amazonaws.com",
    "eudbjx6mig.execute-api.us-east-1.amazonaws.com",
    "q8hqllbg6k.execute-api.us-east-1.amazonaws.com",
    "hhf8nn71vb.execute-api.us-east-1.amazonaws.com",

    # Gateway API Gateway (per region)
    "u433g9r00c.execute-api.eu-central-1.amazonaws.com",
    "j4n6whncmi.execute-api.sa-east-1.amazonaws.com",
    "0prplal5u1.execute-api.us-east-1.amazonaws.com",
    "v7irlu1nrl.execute-api.us-west-2.amazonaws.com",
    "ep1m9qoir8.execute-api.ap-southeast-2.amazonaws.com",

    # JavelinGatewayServiceV2 (per region)
    "8otrnl8e8d.execute-api.eu-central-1.amazonaws.com",
    "ei4rb8pwvd.execute-api.sa-east-1.amazonaws.com",
    "3khxmonavl.execute-api.us-east-1.amazonaws.com",
    "mwsyzhfoe5.execute-api.us-west-2.amazonaws.com",
    "9jlv7mxmw1.execute-api.ap-southeast-2.amazonaws.com",

    # Content/CMS
    "d1hkbwzm1bktgo.cloudfront.net",
    "client.content-service.amazongames.com",
    "client.catalogservice.amazongames.com",
    "client.entitlementservice.amazongames.com",
    "client.agsprivacysettingsservice.amazongames.com",

    # OmniSDK
    "tokenservice.amazongames.com",

    # S3 remote config
    "ags-javelin-remote-config.s3.amazonaws.com",
    "s3.amazonaws.com",

    # AWS generic
    "sts.us-east-1.amazonaws.com",
    "kinesis.us-east-1.amazonaws.com",
    "kinesis.us-west-2.amazonaws.com",

    # Fallbacks
    "localhost",
    "127.0.0.1",
]


def _openssl(*args) -> None:
    result = subprocess.run(["openssl", *args], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[!] openssl failed: {' '.join(args)}")
        print(result.stderr)
        sys.exit(1)


def generate(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    ca_key = out_dir / "newworld_ca.key"
    ca_crt = out_dir / "newworld_ca.crt"
    srv_key = out_dir / "auth.key"
    srv_csr = out_dir / "auth.csr"
    srv_crt = out_dir / "auth.crt"
    ext_cfg = out_dir / "auth.ext"

    # 1. CA key + self-signed CA cert.
    print("[*] Generating root CA...")
    _openssl("req", "-x509", "-newkey", "rsa:2048", "-sha256", "-nodes",
             "-keyout", str(ca_key), "-out", str(ca_crt),
             "-days", "3650",
             "-subj", "/C=US/O=NewWorldPrivate/OU=Dev/CN=NewWorldPrivate Root CA")

    # 2. Server key + CSR.
    print("[*] Generating server CSR...")
    _openssl("req", "-new", "-newkey", "rsa:2048", "-nodes",
             "-keyout", str(srv_key), "-out", str(srv_csr),
             "-subj", "/C=US/O=Amazon/OU=Amazon Game Studios/CN=newworld-auth")

    # 3. SAN extension file.
    san_lines = [f"DNS.{i+1} = {h}" for i, h in enumerate(AUTH_HOSTS)]
    ext_cfg.write_text(
        "authorityKeyIdentifier=keyid,issuer\n"
        "basicConstraints=CA:FALSE\n"
        "keyUsage = digitalSignature, nonRepudiation, keyEncipherment, dataEncipherment\n"
        "extendedKeyUsage = serverAuth\n"
        "subjectAltName = @alt_names\n"
        "[alt_names]\n"
        + "\n".join(san_lines) + "\n"
    )

    # 4. Sign server cert with the CA.
    print("[*] Signing server cert with root CA...")
    _openssl("x509", "-req", "-in", str(srv_csr),
             "-CA", str(ca_crt), "-CAkey", str(ca_key), "-CAcreateserial",
             "-out", str(srv_crt), "-days", "825", "-sha256",
             "-extfile", str(ext_cfg))

    # Cleanup.
    srv_csr.unlink(missing_ok=True)
    (out_dir / "newworld_ca.srl").unlink(missing_ok=True)

    print()
    print(f"[+] CA cert:     {ca_crt}")
    print(f"[+] CA key:      {ca_key}")
    print(f"[+] Server cert: {srv_crt}")
    print(f"[+] Server key:  {srv_key}")
    print(f"    SAN count:   {len(AUTH_HOSTS)}")
    print()
    print("Next: trust the CA in Windows (Admin):")
    print(f"    certutil -addstore -f \"ROOT\" \"{ca_crt}\"")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=str, default=str(CERTS_DIR))
    args = ap.parse_args()
    generate(Path(args.out_dir))
