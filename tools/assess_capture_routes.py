"""
Assess the repo's current DTLS/Javelin capture and decryption routes.

This is a lightweight auditor for the current project state. It does not
attempt any live capture; it just checks for the artifacts and evidence that
would make each route useful today.

Usage:
    python tools/assess_capture_routes.py
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
CAPTURE_DIR = PROJECT_DIR / "capture"
TOOLS_DIR = PROJECT_DIR / "tools"


@dataclass
class RouteAssessment:
    name: str
    status: str
    evidence: list[str]
    next_step: str


def has_nonempty(path: Path) -> bool:
    return path.exists() and path.is_file() and path.stat().st_size > 0


def find_matches(root: Path, patterns: tuple[str, ...]) -> list[Path]:
    matches: list[Path] = []
    if not root.exists():
        return matches
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        lowered = path.name.lower()
        if any(pattern in lowered for pattern in patterns):
            matches.append(path)
    return matches


def read_text_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def assess_sslkeylog() -> RouteAssessment:
    keylog_candidates = find_matches(CAPTURE_DIR, ("sslkeys.log", "keylog", "client_random"))
    nonempty = [p for p in keylog_candidates if has_nonempty(p)]
    evidence = [
        f"Found {len(keylog_candidates)} keylog-like files under capture/."
    ]
    if nonempty:
        evidence.append(
            "At least one candidate keylog file is non-empty: "
            + ", ".join(str(p.relative_to(PROJECT_DIR)) for p in nonempty[:3])
        )
        return RouteAssessment(
            name="SSLKEYLOGFILE",
            status="usable",
            evidence=evidence,
            next_step="Verify whether Wireshark/OpenSSL can decrypt the DTLS captures with the recovered secrets.",
        )
    evidence.append("No non-empty SSL key log or CLIENT_RANDOM artifact exists in the repo.")
    evidence.append("tools/capture_session.py only sets SSLKEYLOGFILE; existing captures show no usable output from that path.")
    return RouteAssessment(
        name="SSLKEYLOGFILE",
        status="blocked",
        evidence=evidence,
        next_step="Only worth revisiting on a non-EAC or alternate runtime where the client actually emits key logs.",
    )


def assess_frida() -> RouteAssessment:
    hooks_log = CAPTURE_DIR / "20260416_224201_dtls_test" / "hooks.log"
    hooks_text = read_text_if_exists(hooks_log)
    evidence = [
        f"frida_capture tooling exists: {TOOLS_DIR / 'frida_capture.py'}",
        f"hook script exists: {TOOLS_DIR / 'frida_dtls_hook.js'}",
    ]
    if "SSL_read" in hooks_text or "not_found" in hooks_text:
        snippet = "; ".join(line.strip() for line in hooks_text.splitlines()[:5] if line.strip())
        if snippet:
            evidence.append(f"Stored hook attempt evidence: {snippet}")
    evidence.append("Live Frida attach against NewWorld.exe previously failed with VirtualAllocEx ACCESS_DENIED.")
    return RouteAssessment(
        name="Frida/OpenSSL hook",
        status="blocked",
        evidence=evidence,
        next_step="Only revisit on a non-EAC-friendly target or with a different in-process load path that avoids remote injection.",
    )


def assess_dtls_proxy() -> RouteAssessment:
    evidence = [
        f"DTLS MITM tooling exists: {TOOLS_DIR / 'dtls_proxy.py'}",
        f"UDP redirect tooling exists: {TOOLS_DIR / 'udp_redirect.py'}",
        "Live local-proxy path reached real DTLS handshake, but the client rejected our certificate with fatal unknown ca.",
    ]
    return RouteAssessment(
        name="Local DTLS MITM proxy",
        status="blocked",
        evidence=evidence,
        next_step="Requires a trust-bypass or a client environment that accepts our probe certificate; not currently viable on the live EAC path.",
    )


def assess_transport_only() -> RouteAssessment:
    tap_packets = CAPTURE_DIR / "20260416_231434_tap_test" / "packets.jsonl"
    evidence = [
        f"Transport interception tools exist: {TOOLS_DIR / 'dtls_intercept.py'}, {TOOLS_DIR / 'udp_probe.py'}",
        "Existing tap capture proves we can observe raw DTLS records and packet timing.",
    ]
    if has_nonempty(tap_packets):
        evidence.append(f"Non-empty raw tap artifact: {tap_packets.relative_to(PROJECT_DIR)}")
    return RouteAssessment(
        name="Transport-only capture (WinDivert/UDP probe)",
        status="usable_for_metadata_only",
        evidence=evidence,
        next_step="Keep using this for timing, sizes, and sequence analysis, but it will not produce decrypted Javelin payloads without session secrets.",
    )


def assess_offline_pcap() -> RouteAssessment:
    pcaps = [
        CAPTURE_DIR / "20260416_221806_first_capture" / "pcaps" / "capture.pcapng",
        CAPTURE_DIR / "20260416_222545_second_capture" / "pcaps" / "capture.pcapng",
    ]
    existing = [p for p in pcaps if has_nonempty(p)]
    evidence = [
        f"Offline DTLS analysis tools exist: {TOOLS_DIR / 'analyze_pcapng_dtls.py'}, {TOOLS_DIR / 'extract_registration_window.py'}",
        "Existing real captures already isolate the stable encrypted REP registration window.",
    ]
    if existing:
        evidence.append(
            "Useful captures: " + ", ".join(str(p.relative_to(PROJECT_DIR)) for p in existing)
        )
    return RouteAssessment(
        name="Offline pcapng analysis",
        status="best_current_route",
        evidence=evidence,
        next_step="Use the captures to target the first decryptable server application-data window while searching for a non-EAC source of session secrets.",
    )


def main() -> int:
    assessments = [
        assess_sslkeylog(),
        assess_frida(),
        assess_dtls_proxy(),
        assess_transport_only(),
        assess_offline_pcap(),
    ]

    print("DTLS/Javelin capture route audit")
    print("=" * 32)
    for route in assessments:
        print(f"\n[{route.status}] {route.name}")
        for item in route.evidence:
            print(f"  - {item}")
        print(f"  next: {route.next_step}")

    summary = {
        "best_current_route": next(r.name for r in assessments if r.status == "best_current_route"),
        "blocked_routes": [r.name for r in assessments if r.status == "blocked"],
        "metadata_only_routes": [r.name for r in assessments if r.status == "usable_for_metadata_only"],
    }
    print("\nSummary")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
