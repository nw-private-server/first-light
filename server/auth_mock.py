"""
New World HTTPS auth mock.

Stands up a single HTTPS server on port 443 that answers every endpoint
the game client hits during auth + world-config fetch. Routes by Host
header. Logs every request (method, host, path, headers, body) to
console + a session log file so we can iterate on response shapes as
the client reveals what it expects.

Hostnames served (from capture/channel_config.json and the game log):

  Channel service
    d2c74t4zimux3r.cloudfront.net        GET /STEAM_APP_ID.1063730.json

  Regional HTTP Gateways (CloudFront fronts for API Gateway)
    d3bj4csovi1fe8.cloudfront.net        us-west-2
    d2oeuvxi3kfsrw.cloudfront.net        us-east-1
    d1w0bfy6smo4d1.cloudfront.net        eu-central-1
    d1cjlmzk0xrm0z.cloudfront.net        sa-east-1
    de4mfzk9wkelz.cloudfront.net         ap-southeast-2

  Auth stacks (API Gateway direct)
    q8hqllbg6k.execute-api.us-east-1.amazonaws.com    us-west auth
    eudbjx6mig.execute-api.us-east-1.amazonaws.com    us-east auth
    (etc. per region)

  Content
    d1hkbwzm1bktgo.cloudfront.net        /motd/worlds_*.json
                                          /newsstories/*/metadata.json
                                          /marketingtiles/*/metadata.json
    client.content-service.amazongames.com/images/... (images)
    client.catalogservice.amazongames.com
    client.entitlementservice.amazongames.com
    client.agsprivacysettingsservice.amazongames.com

  OmniSDK
    tokenservice.amazongames.com

  S3 remote config
    ags-javelin-remote-config.s3.amazonaws.com
      /applications/{scope}/configuration-sets/WorldId/{worldId}/{version}

Usage:
    python -m server.auth_mock --port 443

Requires Administrator on Windows for port 443 and for trusting the CA.
"""

from __future__ import annotations

import argparse
import json
import socketserver
import ssl
import sys
import threading
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

PROJECT_DIR = Path(__file__).resolve().parent.parent
CAPTURE_DIR = PROJECT_DIR / "capture"
CERTS_DIR = PROJECT_DIR / "server" / "certs"
LOGS_DIR = PROJECT_DIR / "capture" / "auth_mock_logs"
CHANNEL_CONFIG = CAPTURE_DIR / "channel_config.json"

# Where we point the client's REP (game server) address. The game will
# try to open a DTLS connection here after passing auth.
DEFAULT_REP_HOST = "127.0.0.1"
DEFAULT_REP_PORT = 23971


# ---------------------------------------------------------------------------
#  Logging
# ---------------------------------------------------------------------------

_LOG_LOCK = threading.Lock()


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def log(msg: str) -> None:
    with _LOG_LOCK:
        line = f"[{_ts()}] {msg}"
        print(line)
        try:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            (LOGS_DIR / f"{datetime.now().strftime('%Y%m%d')}.log").open("a", encoding="utf-8").write(line + "\n")
        except Exception:
            pass


# ---------------------------------------------------------------------------
#  Canned response builders
# ---------------------------------------------------------------------------

def build_channel_config(rep_host: str, rep_port: int) -> dict:
    """Return the channel service JSON. Prefer loading the real one from
    capture/channel_config.json; fall back to a minimal synthetic version
    if the file doesn't exist."""
    if CHANNEL_CONFIG.exists():
        return json.loads(CHANNEL_CONFIG.read_text(encoding="utf-8"))
    # Minimal fallback.
    return {
        "channelName": "Retail",
        "pdx-prod": {
            "displayName": "US West",
            "localizedName": "@mm_us_west",
            "poolId": "us-east-1:3be8c78b-1be2-43b6-bfab-515cc6cfcc3f",
            "publicApis": [
                {
                    "awsRegion": "us-east-1",
                    "version": "1.0",
                    "apiEndpoint": "q8hqllbg6k.execute-api.us-east-1.amazonaws.com",
                    "clientTag": "authStack",
                    "stage": "prod",
                },
                {
                    "awsRegion": "us-west-2",
                    "version": "1.0",
                    "apiEndpoint": "d3bj4csovi1fe8.cloudfront.net",
                    "clientTag": "JavelinGatewayService-CF",
                },
            ],
        },
        "platformMetadata": {
            "OMNI.STEAM_APP_ID.1063730": {
                "omniTokenUrl": "https://tokenservice.amazongames.com",
                "omniStage": "prod",
                "omniGameAlias": "new-world",
            },
        },
    }


def make_fake_credentials(kind: str) -> dict:
    """Mint an STS-shaped set of temporary credentials."""
    now = datetime.now(timezone.utc)
    expiry = now + timedelta(hours=1)
    return {
        "accessKeyId": f"ASIA{kind.upper()[:4]}FAKEKEY{uuid.uuid4().hex[:12].upper()}",
        "secretAccessKey": uuid.uuid4().hex + uuid.uuid4().hex[:8],
        "sessionToken": (uuid.uuid4().hex + uuid.uuid4().hex
                         + uuid.uuid4().hex)[:384],
        "expiration": expiry.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
    }


def make_fake_login_ticket(world_id: str | None = None) -> dict:
    """Build a login-queue response that contains a ticket of the right shape.
    Observed in game logs: '<worldId>_<ticketId>' where both are UUIDs."""
    world_id = world_id or "eacab29f-f0eb-43b4-84ed-91c4861aefc0"  # live-2-02-1
    ticket_id = str(uuid.uuid4())
    return {
        "ticket": f"{world_id}_{ticket_id}",
        "worldId": world_id,
        "worldName": "live-private-01",
        "repAddress": f"{DEFAULT_REP_HOST}:{DEFAULT_REP_PORT}",
        "location": "",
        "status": "Granted",
    }


# ---------------------------------------------------------------------------
#  Route table
#
#  Each route is (host_pattern, method, path_pattern_fn, handler).
#  host_pattern is a string that must equal the Host header, or "*".
#  path_pattern_fn(path) returns True if the route handles this path.
# ---------------------------------------------------------------------------


def _path_eq(p: str):
    return lambda path: path == p


def _path_prefix(prefix: str):
    return lambda path: path.startswith(prefix)


def _path_endswith(suffix: str):
    return lambda path: path.endswith(suffix)


# ---------------------------------------------------------------------------
#  Handler implementations
# ---------------------------------------------------------------------------


class Ctx:
    """Per-request context carrying server options into handlers."""

    def __init__(self, rep_host: str, rep_port: int):
        self.rep_host = rep_host
        self.rep_port = rep_port


def handle_channel_service(ctx: Ctx, handler: "AuthHandler"):
    body = json.dumps(build_channel_config(ctx.rep_host, ctx.rep_port)).encode()
    handler._respond(200, body, content_type="application/json")


def handle_credentials_omni(ctx: Ctx, handler: "AuthHandler"):
    body = json.dumps({
        "gatewayCredentials": make_fake_credentials("gw"),
        "personaCredentials": make_fake_credentials("pp"),
        "personaId": "amzn1.developerPersonaId." + str(uuid.uuid4()),
        "accountType": "Full",
        "ownership": "permanent",
    }).encode()
    handler._respond(200, body, content_type="application/json")


def handle_login_queue(ctx: Ctx, handler: "AuthHandler"):
    body = json.dumps(make_fake_login_ticket()).encode()
    handler._respond(200, body, content_type="application/json")


def handle_remote_config(ctx: Ctx, handler: "AuthHandler"):
    """S3 ags-javelin-remote-config: returns minimal config blobs."""
    handler._respond(200, b"{}", content_type="application/json")


def handle_worlds_motd(ctx: Ctx, handler: "AuthHandler"):
    body = json.dumps({"worlds": [], "overrides": {}}).encode()
    handler._respond(200, body, content_type="application/json")


def handle_news_metadata(ctx: Ctx, handler: "AuthHandler"):
    body = json.dumps({"stories": []}).encode()
    handler._respond(200, body, content_type="application/json")


def handle_marketing_metadata(ctx: Ctx, handler: "AuthHandler"):
    body = json.dumps({"tiles": []}).encode()
    handler._respond(200, body, content_type="application/json")


def handle_omni_token(ctx: Ctx, handler: "AuthHandler"):
    """Fake OmniSDK token service response.

    Path observed: POST https://tokenservice.amazongames.com/games/new-world/tokens
    The client sends its Steam session ticket + an Amazon-signed fallbackToken.
    OmniSDK expects back a full session creation payload: a persona id,
    an ags account type, a session token, and a bearer token. If any
    required field is missing OmniSDK reports 'CreateSession failed'.

    Field names are best-effort guesses — the game log logs the RESULT
    ('Get persona id result: OK', 'Get ags account type result: Full',
    'Omni CreateSession complete with result: 0, id: amzn1.developerPersonaId.*')
    but not the raw JSON keys. Iterate based on client response.
    """
    persona_id = "amzn1.developerPersonaId." + str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    # OmniSDK appears to like both snake_case and camelCase — return both
    # shapes for each field. The client deserializer will pick whichever it
    # has bindings for and ignore the rest.
    body = json.dumps({
        # Persona identification
        "personaId": persona_id,
        "persona_id": persona_id,
        "id": persona_id,

        # AGS account type (log shows 'Full')
        "agsAccountType": "Full",
        "ags_account_type": "Full",
        "accountType": "Full",

        # Session / ownership
        "sessionId": session_id,
        "session_id": session_id,
        "ownership": "permanent",

        # Bearer token for subsequent calls to credentials endpoint
        "token": uuid.uuid4().hex,
        "access_token": uuid.uuid4().hex,
        "expiresIn": 3600,
        "expires_in": 3600,
        "tokenType": "Bearer",
        "token_type": "Bearer",

        # Result code — 0 = OK per the game log
        "result": 0,
        "resultCode": 0,
        "status": "OK",

        # Timestamps (some AWS SDK consumers insist on expiration strings)
        "issuedAt": now.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "expiration": (now + timedelta(seconds=3600)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
    }).encode()
    handler._respond(200, body, content_type="application/json")


def handle_unknown(ctx: Ctx, handler: "AuthHandler"):
    """Catch-all: return an empty JSON object so the client doesn't crash.
    The goal here is to KEEP the client progressing so we can see what it
    asks for next."""
    handler._respond(200, b"{}", content_type="application/json")


# Routes are matched in order. First match wins.
ROUTES = [
    # Channel service
    ("d2c74t4zimux3r.cloudfront.net", "GET", _path_endswith(".json"), handle_channel_service),

    # Credentials (omni)
    ("*", "POST", _path_endswith("/credentials/omni"), handle_credentials_omni),
    ("*", "GET", _path_endswith("/credentials/omni"), handle_credentials_omni),

    # Login queue (observed endpoint is under /prod/users/login_queue/* on the gateway)
    ("*", "POST", _path_prefix("/prod/users/login_queue"), handle_login_queue),
    ("*", "GET", _path_prefix("/prod/users/login_queue"), handle_login_queue),

    # Remote config (S3)
    ("ags-javelin-remote-config.s3.amazonaws.com", "GET", _path_prefix("/applications/"), handle_remote_config),

    # Content bundles
    ("d1hkbwzm1bktgo.cloudfront.net", "GET", _path_prefix("/motd/"), handle_worlds_motd),
    ("d1hkbwzm1bktgo.cloudfront.net", "GET", _path_prefix("/newsstories/"), handle_news_metadata),
    ("d1hkbwzm1bktgo.cloudfront.net", "GET", _path_prefix("/marketingtiles/"), handle_marketing_metadata),

    # OmniSDK token service
    ("tokenservice.amazongames.com", "*", lambda p: True, handle_omni_token),
]


# ---------------------------------------------------------------------------
#  HTTP handler
# ---------------------------------------------------------------------------


class AuthHandler(BaseHTTPRequestHandler):
    # Suppress default stderr logging — we use our own.
    def log_message(self, format, *args):
        return

    # Context is attached to the server instance.
    @property
    def ctx(self) -> Ctx:
        return self.server.ctx  # type: ignore

    def _extract_host(self) -> str:
        host = self.headers.get("Host", "")
        # Strip port if present.
        if ":" in host:
            host = host.split(":", 1)[0]
        return host.lower()

    def _extract_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0") or 0)
        return self.rfile.read(length) if length else b""

    def _log_request(self, body: bytes) -> None:
        host = self._extract_host()
        log(f"REQ {self.command} https://{host}{self.path}  "
            f"client={self.client_address[0]}")
        for h, v in self.headers.items():
            if h.lower() in ("authorization", "x-amz-date", "x-amz-security-token"):
                v = v[:40] + "..." if len(v) > 40 else v
            log(f"    < {h}: {v}")
        if body:
            try:
                snippet = body.decode("utf-8", errors="replace")
                if len(snippet) > 1000:
                    snippet = snippet[:1000] + "...[truncated]"
                log(f"    < BODY: {snippet}")
            except Exception:
                log(f"    < BODY: <{len(body)} bytes binary>")

    def _respond(self, status: int, body: bytes, *, content_type: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        try:
            snippet = body[:500].decode("utf-8", errors="replace")
            log(f"    > {status} {content_type}  {len(body)}B")
            if body:
                log(f"    > {snippet}")
        except Exception:
            log(f"    > {status} {content_type}  {len(body)}B")

    def _dispatch(self) -> None:
        host = self._extract_host()
        body = self._extract_body()
        self._log_request(body)

        for (host_pat, method_pat, path_fn, handler) in ROUTES:
            if host_pat != "*" and host_pat != host:
                continue
            if method_pat != "*" and method_pat != self.command:
                continue
            if not path_fn(self.path):
                continue
            try:
                handler(self.ctx, self)
                return
            except Exception as e:
                log(f"    ! handler error: {e}")
                self._respond(500, b"{}", content_type="application/json")
                return

        log(f"    ! no route matched, returning {{}} (host={host})")
        handle_unknown(self.ctx, self)

    def do_GET(self):
        self._dispatch()

    def do_POST(self):
        self._dispatch()

    def do_PUT(self):
        self._dispatch()

    def do_DELETE(self):
        self._dispatch()


class ThreadedHTTPSServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address, RequestHandlerClass, ctx: Ctx,
                 ssl_ctx: ssl.SSLContext):
        super().__init__(server_address, RequestHandlerClass)
        self.ctx = ctx
        self.ssl_ctx = ssl_ctx

    def get_request(self):
        sock, addr = super().get_request()
        try:
            ssl_sock = self.ssl_ctx.wrap_socket(sock, server_side=True)
        except ssl.SSLError as e:
            log(f"[!] SSL handshake error from {addr}: {e}")
            raise
        return ssl_sock, addr


# ---------------------------------------------------------------------------
#  Entrypoint
# ---------------------------------------------------------------------------


def build_ssl_context(cert: Path, key: Path) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(certfile=str(cert), keyfile=str(key))
    return ctx


def main() -> None:
    ap = argparse.ArgumentParser(description="New World HTTPS auth mock")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=443)
    ap.add_argument("--cert", default=str(CERTS_DIR / "auth.crt"))
    ap.add_argument("--key", default=str(CERTS_DIR / "auth.key"))
    ap.add_argument("--rep-host", default=DEFAULT_REP_HOST,
                    help="Game-server IP to hand back in login tickets")
    ap.add_argument("--rep-port", type=int, default=DEFAULT_REP_PORT,
                    help="Game-server port to hand back in login tickets")
    args = ap.parse_args()

    cert = Path(args.cert)
    key = Path(args.key)
    if not cert.exists() or not key.exists():
        print("[!] Missing HTTPS cert/key.")
        print(f"    Expected: {cert}")
        print(f"    Expected: {key}")
        print("    Run: python tools/generate_auth_certs.py")
        sys.exit(1)

    ctx = Ctx(args.rep_host, args.rep_port)
    ssl_ctx = build_ssl_context(cert, key)

    server = ThreadedHTTPSServer((args.host, args.port), AuthHandler, ctx, ssl_ctx)

    log("[*] HTTPS auth mock starting")
    log(f"    Bind:    {args.host}:{args.port}")
    log(f"    Cert:    {cert}")
    log(f"    REP:     {args.rep_host}:{args.rep_port}  (returned in login tickets)")
    log("    Logs:    " + str(LOGS_DIR))
    log("")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("[*] stopping.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
