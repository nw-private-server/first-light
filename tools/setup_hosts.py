r"""
Manage the Windows hosts file to redirect New World's auth hostnames
to our local auth mock.

Safe-by-default: prints the lines it WOULD add and the current state.
Use --apply to actually modify the file (requires Administrator).
Use --revert to remove our block.

hosts file location:
    C:\Windows\System32\drivers\etc\hosts
"""

from __future__ import annotations

import argparse
import ctypes
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

HOSTS_PATH = Path(r"C:\Windows\System32\drivers\etc\hosts")

BLOCK_BEGIN = "# >>> NewWorldPrivate auth-mock redirects >>>"
BLOCK_END = "# <<< NewWorldPrivate auth-mock redirects <<<"

# Same list as tools/generate_auth_certs.py's AUTH_HOSTS. Kept in sync
# manually; if it drifts, worst case a host doesn't get redirected.
REDIRECT_HOSTS = [
    "d2c74t4zimux3r.cloudfront.net",
    "d1w0bfy6smo4d1.cloudfront.net",
    "d1cjlmzk0xrm0z.cloudfront.net",
    "d2oeuvxi3kfsrw.cloudfront.net",
    "d3bj4csovi1fe8.cloudfront.net",
    "de4mfzk9wkelz.cloudfront.net",
    "2mfrik7h83.execute-api.us-east-1.amazonaws.com",
    "kqqt5twsi7.execute-api.us-east-1.amazonaws.com",
    "eudbjx6mig.execute-api.us-east-1.amazonaws.com",
    "q8hqllbg6k.execute-api.us-east-1.amazonaws.com",
    "hhf8nn71vb.execute-api.us-east-1.amazonaws.com",
    "u433g9r00c.execute-api.eu-central-1.amazonaws.com",
    "j4n6whncmi.execute-api.sa-east-1.amazonaws.com",
    "0prplal5u1.execute-api.us-east-1.amazonaws.com",
    "v7irlu1nrl.execute-api.us-west-2.amazonaws.com",
    "ep1m9qoir8.execute-api.ap-southeast-2.amazonaws.com",
    "8otrnl8e8d.execute-api.eu-central-1.amazonaws.com",
    "ei4rb8pwvd.execute-api.sa-east-1.amazonaws.com",
    "3khxmonavl.execute-api.us-east-1.amazonaws.com",
    "mwsyzhfoe5.execute-api.us-west-2.amazonaws.com",
    "9jlv7mxmw1.execute-api.ap-southeast-2.amazonaws.com",
    "d1hkbwzm1bktgo.cloudfront.net",
    "client.content-service.amazongames.com",
    "client.catalogservice.amazongames.com",
    "client.entitlementservice.amazongames.com",
    "client.agsprivacysettingsservice.amazongames.com",
    "tokenservice.amazongames.com",
    "ags-javelin-remote-config.s3.amazonaws.com",
]


def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0  # type: ignore[attr-defined]
    except Exception:
        return False


def build_block(target_ip: str, target_ip6: str = "::1") -> str:
    lines = [BLOCK_BEGIN, f"# Added {datetime.now().isoformat(timespec='seconds')}"]
    for h in REDIRECT_HOSTS:
        lines.append(f"{target_ip}\t{h}")
    if target_ip6:
        # Stubbed-mode gateway client may prefer IPv6 (AF_INET6 sockets seen in
        # Frida traces 2026-04-26). Add ::1 entries so the AAAA record also
        # resolves to localhost; otherwise the resolver returns the real
        # cloudfront IPv6 addr and our hosts redirect is bypassed.
        for h in REDIRECT_HOSTS:
            lines.append(f"{target_ip6}\t{h}")
    lines.append(BLOCK_END)
    return "\n".join(lines) + "\n"


def read_hosts() -> str:
    return HOSTS_PATH.read_text(encoding="utf-8")


def strip_block(content: str) -> str:
    if BLOCK_BEGIN not in content:
        return content
    before, _, rest = content.partition(BLOCK_BEGIN)
    _, _, after = rest.partition(BLOCK_END)
    # Clean up any leftover newlines.
    return (before.rstrip() + "\n" + after.lstrip()).strip("\n") + "\n"


def backup_hosts() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = HOSTS_PATH.with_suffix(f".bak_{stamp}")
    shutil.copy2(HOSTS_PATH, backup)
    return backup


def cmd_status() -> None:
    content = read_hosts()
    has = BLOCK_BEGIN in content
    print(f"[*] hosts file: {HOSTS_PATH}")
    print(f"[*] block present: {'YES' if has else 'no'}")
    if has:
        start = content.find(BLOCK_BEGIN)
        end = content.find(BLOCK_END)
        if start >= 0 and end >= 0:
            print()
            print(content[start:end + len(BLOCK_END)])


def cmd_dry_run(target_ip: str) -> None:
    print(f"[*] Would add/replace block in: {HOSTS_PATH}")
    print(f"[*] Target IP: {target_ip}")
    print()
    print(build_block(target_ip))
    print("Run with --apply (as Administrator) to actually modify the file.")


def cmd_apply(target_ip: str) -> None:
    if not is_admin():
        print("[!] Must run as Administrator to modify hosts file.")
        sys.exit(1)
    content = read_hosts()
    content = strip_block(content)
    content = content.rstrip() + "\n\n" + build_block(target_ip)
    backup = backup_hosts()
    print(f"[+] Backed up hosts file -> {backup}")
    HOSTS_PATH.write_text(content, encoding="utf-8")
    print(f"[+] Wrote {len(REDIRECT_HOSTS)} redirects pointing at {target_ip}.")
    print("[+] Flush DNS cache: ipconfig /flushdns")


def cmd_revert() -> None:
    if not is_admin():
        print("[!] Must run as Administrator to modify hosts file.")
        sys.exit(1)
    content = read_hosts()
    if BLOCK_BEGIN not in content:
        print("[*] No auth-mock block found. Nothing to do.")
        return
    new = strip_block(content)
    backup = backup_hosts()
    print(f"[+] Backed up hosts file -> {backup}")
    HOSTS_PATH.write_text(new, encoding="utf-8")
    print(f"[+] Removed auth-mock block.")
    print("[+] Flush DNS cache: ipconfig /flushdns")


def main() -> None:
    ap = argparse.ArgumentParser(description="Manage hosts-file redirects for the auth mock")
    ap.add_argument("--apply", action="store_true", help="Write the block to the hosts file (admin)")
    ap.add_argument("--revert", action="store_true", help="Remove our block from the hosts file (admin)")
    ap.add_argument("--target", default="127.0.0.1",
                    help="IP to point the hostnames at (default 127.0.0.1)")
    args = ap.parse_args()

    if args.revert:
        cmd_revert()
        return

    if args.apply:
        cmd_apply(args.target)
        cmd_status()
        return

    # Default: dry-run + status.
    cmd_status()
    print()
    cmd_dry_run(args.target)


if __name__ == "__main__":
    main()
