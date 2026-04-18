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
import base64
import json
import socketserver
import ssl
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

import jwt as pyjwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

PROJECT_DIR = Path(__file__).resolve().parent.parent
CAPTURE_DIR = PROJECT_DIR / "capture"
CERTS_DIR = PROJECT_DIR / "server" / "certs"
LOGS_DIR = PROJECT_DIR / "capture" / "auth_mock_logs"
CHANNEL_CONFIG = CAPTURE_DIR / "channel_config.json"

# Where we point the client's REP (game server) address. The game will
# try to open a DTLS connection here after passing auth.
DEFAULT_REP_HOST = "127.0.0.1"
DEFAULT_REP_PORT = 23971

# JWT signing
JWT_SIGNING_KEY_PATH = CERTS_DIR / "jwt_signing.key"
JWT_SIGNING_PUB_PATH = CERTS_DIR / "jwt_signing.pub"
JWT_KID = "nwprivate-auth-1"     # our key id
JWT_ISSUER = "https://tokenservice.amazongames.com"


def _load_signing_key() -> rsa.RSAPrivateKey:
    if not JWT_SIGNING_KEY_PATH.exists():
        raise FileNotFoundError(
            f"JWT signing key missing at {JWT_SIGNING_KEY_PATH}. "
            f"Run: cd server/certs && openssl genrsa -out jwt_signing.key 2048"
        )
    return serialization.load_pem_private_key(
        JWT_SIGNING_KEY_PATH.read_bytes(), password=None
    )


def _load_signing_pub() -> rsa.RSAPublicKey:
    if JWT_SIGNING_PUB_PATH.exists():
        return serialization.load_pem_public_key(JWT_SIGNING_PUB_PATH.read_bytes())
    # Derive from private key if .pub wasn't generated.
    priv = _load_signing_key()
    return priv.public_key()


def _int_to_b64url(n: int) -> str:
    byte_len = (n.bit_length() + 7) // 8
    return base64.urlsafe_b64encode(n.to_bytes(byte_len, "big")).decode().rstrip("=")


def build_jwks() -> dict:
    """Return the JWKS payload advertising our RSA signing key."""
    pub = _load_signing_pub()
    numbers = pub.public_numbers()
    return {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "alg": "RS256",
                "kid": JWT_KID,
                "n": _int_to_b64url(numbers.n),
                "e": _int_to_b64url(numbers.e),
            }
        ]
    }


def sign_jwt(persona_id: str, extra: dict | None = None, ttl_seconds: int = 3600) -> str:
    """Mint a signed JWT that OmniSDK will accept as a session/access token."""
    now = int(time.time())
    payload = {
        "sub": persona_id,
        "iss": JWT_ISSUER,
        "aud": "new-world",
        "iat": now,
        "exp": now + ttl_seconds,
        "nbf": now - 30,
        "az_platform_name": "steam",
        "az_ags_identity_type": "Full",
        "ags_account_type": "Full",
    }
    if extra:
        payload.update(extra)
    jku = f"{JWT_ISSUER}/games/new-world/.well-known/openid-configuration/jwks.json"
    key = _load_signing_key()
    token = pyjwt.encode(
        payload,
        key,
        algorithm="RS256",
        headers={"kid": JWT_KID, "jku": jku, "typ": "JWT"},
    )
    return token


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
    """Mint an STS-shaped set of temporary credentials.

    Real AWS STS: accessKeyId is exactly 20 chars (ASIA + 16 [A-Z0-9]);
    secretAccessKey is 40 chars of base64 alphabet; expiration has no
    fractional seconds. The AWS C++ SDK validates shape before signing."""
    import base64, secrets
    del kind  # kept for callsite clarity; no longer affects key format
    now = datetime.now(timezone.utc)
    expiry = now + timedelta(hours=1)
    b32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    key_tail = "".join(secrets.choice(b32) for _ in range(16))
    secret = base64.b64encode(secrets.token_bytes(30)).decode()  # 40 chars
    token = base64.b64encode(secrets.token_bytes(288)).decode()  # ~384 chars
    return {
        "accessKeyId": f"ASIA{key_tail}",
        "secretAccessKey": secret,
        "sessionToken": token,
        "expiration": expiry.strftime("%Y-%m-%dT%H:%M:%SZ"),
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
    """Schema confirmed from FUN_145a955e0 (SteamAuth response handler).
    The parser reads four FLAT top-level fields off the document — no
    gatewayCredentials/personaCredentials wrapper. Offsets in the resulting
    credentials object: accessKeyId @ 0x10, secretAccessKey @ 0x30,
    sessionToken @ 0x50, expiration parsed into a chrono::time_point @ 0x70."""
    body = json.dumps(make_fake_credentials("omni")).encode()
    handler._respond(200, body, content_type="application/json")


def handle_login_queue(ctx: Ctx, handler: "AuthHandler"):
    body = json.dumps(make_fake_login_ticket()).encode()
    handler._respond(200, body, content_type="application/json")


def handle_get_login_info(ctx: Ctx, handler: "AuthHandler"):
    """GET /prod/game/getlogininfo/jwt/omni?channelId=...&includeNames=true

    Schema resolved from FUN_144f40780 RPC schema table (NewWorld.exe
    0x144f54a21-0x144f554cd). Response type is WorldsInfo containing
    `worlds` (list[WorldMetadata]) and `recommendedWorlds`
    (list[RecommendedWorld]). WorldMetadata inherits common fields
    (personaId, name, region, channel, creationDate, modifiedDate) from
    a base entity type and adds world-specific fields + nested
    WorldMetrics. No top-level `characters` field: character data comes
    later via a separate call after a world is selected.

    Seeding one placeholder world so the UI shows 'Create Character'."""
    # WorldMetadata = only world-specific fields. The base-class fields
    # (personaId, name, region, channel, creationDate, modifiedDate) belong
    # to CharacterMetadata's parent entity; shoving them onto worlds caused
    # a CTD during character-select rendering. Enum-looking fields (type,
    # status, publicStatusCode, worldPopulationStatus) are almost certainly
    # integer codes — the RPC schema registered them with different helpers
    # than the string fields.
    world = {
        "worldId": "eacab29f-f0eb-43b4-84ed-91c4861aefc0",
        "type": 0,
        "status": 0,
        "publicStatusCode": 0,
        "publicName": "Valhalla",
        "version": "1.0.0",
        "maxAccountCharacters": 10,
        "worldSet": "live",
        "worldMetrics": {
            "worldAgeDays": 0,
            "queueSize": 0,
            "queueWaitTimeSec": 0,
            "worldPopulationStatus": 0,
        },
        "transferToRegion": "",
        "isFull": False,
        "isRecommended": True,
    }

    # WorldsInfo only has worlds + recommendedWorlds. The fields that
    # looked like top-level (personaId, region, channel, creationDate,
    # modifiedDate) are actually CharacterMetadata's inherited base class
    # fields — putting them at response root was causing a delayed CTD
    # after the initial character-select render.
    body = json.dumps({
        "worlds": [world],
        "recommendedWorlds": [],
    }).encode()
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

    Schema confirmed from FUN_1479b6d00 (ags_fed_acc_token.cpp) + child
    validators FUN_1479c0fd0 (PlatformPersonaAccount) and FUN_1479c0620
    (AgsPersonaAccount). On the success path the parser requires:

      Top-level (all mandatory — missing any yields 0xCB / 203):
        accessToken   : string (JWT)
        fallbackToken : string (JWT)
        platformAccount : object
        account       : object  (absent -> 0x133, still surfaced as error)
        expiresIn     : number (seconds; multiplied x1000 internally)

      platformAccount required keys (FUN_1479c0fd0):
        identityType, identityId, personaId, ageGroup

      account required keys (FUN_1479c0620):
        identityId, personaId, type, ageGroup
        (type is lowercased + compared to "shadow"; use "full" otherwise)

      Optional: limitedUseToken, isNewAccount, suspension,
                conflictingAccount, region, penalties, platform.

    We still echo the request fallbackToken as our token since OmniSDK
    verifies it against Amazon's hardcoded public key — minting our own
    won't pass that check.
    """
    # Parse the request body to extract fallbackToken + sub.
    request_body = handler._last_request_body or b""
    persona_id = "amzn1.developerPersonaId." + str(uuid.uuid4())
    platform_identity_id = str(uuid.uuid4())
    fallback_token = None
    try:
        parsed_req = json.loads(request_body)
        fallback_token = parsed_req.get("fallbackToken")
        if fallback_token:
            # JWTs are three base64url segments. Payload is middle segment.
            parts = fallback_token.split(".")
            if len(parts) >= 2:
                pad = "=" * (-len(parts[1]) % 4)
                payload_bytes = base64.urlsafe_b64decode(parts[1] + pad)
                payload = json.loads(payload_bytes)
                sub = payload.get("sub")
                if sub:
                    persona_id = sub
                    log(f"    * extracted persona from fallbackToken.sub: {persona_id}")
    except Exception as e:
        log(f"    * couldn't parse fallbackToken: {e}")

    # Echo fallbackToken back — Amazon-signed, passes OmniSDK's hardcoded
    # public key verification. Fall back to a self-signed JWT if not present.
    token = fallback_token or sign_jwt(persona_id)

    # IMPORTANT: do NOT include "suspension" or "conflictingAccount" as null.
    # FUN_1479d6860 uses cJSON_GetObjectItemCaseSensitive, which returns truthy
    # for any present key — including null values. A present-but-null
    # "suspension" then flows into FUN_1479c1a40, which rejects non-objects
    # and sets resultCode = 0xCB (203). Same hazard for "conflictingAccount"
    # on the merge-conflict path. Just omit these keys on the success path.
    body = json.dumps({
        "accessToken": token,
        "fallbackToken": token,
        "limitedUseToken": token,
        "expiresIn": 3600,
        "isNewAccount": False,
        "platformAccount": {
            "identityType": "steam",
            "identityId": platform_identity_id,
            "personaId": persona_id,
            "ageGroup": "adult",
            "platform": "steam",
        },
        "account": {
            "identityId": persona_id,
            "personaId": persona_id,
            "type": "full",
            "ageGroup": "adult",
        },
    }).encode()
    handler._respond(200, body, content_type="application/json")


def handle_jwks(ctx: Ctx, handler: "AuthHandler"):
    """Expose our public signing key so OmniSDK can verify our JWTs."""
    body = json.dumps(build_jwks()).encode()
    handler._respond(200, body, content_type="application/json")


def handle_openid_config(ctx: Ctx, handler: "AuthHandler"):
    """Minimal OpenID Connect discovery doc pointing at our JWKS."""
    host = handler._extract_host()
    base = f"https://{host}/games/new-world"
    body = json.dumps({
        "issuer": JWT_ISSUER,
        "jwks_uri": f"{base}/.well-known/openid-configuration/jwks.json",
        "id_token_signing_alg_values_supported": ["RS256"],
        "token_endpoint": f"{base}/tokens",
        "response_types_supported": ["token"],
        "subject_types_supported": ["public"],
    }).encode()
    handler._respond(200, body, content_type="application/json")


def handle_entitlements_sync(ctx: Ctx, handler: "AuthHandler"):
    """POST /players/{personaId}/games/new-world/platforms/steam/entitlements/sync

    Empty {} — the entitlement parser schema is unknown, and our guessed
    shape caused a delayed CTD during character-select rendering. Stable
    {} matched the earlier known-good sessions."""
    handler._respond(200, b"{}", content_type="application/x-amz-json-1.1")


def handle_entitlements_list(ctx: Ctx, handler: "AuthHandler"):
    """GET /players/{personaId}/games/new-world/platforms/steam/entitlements

    Empty {} — same reason. We need Ghidra to extract the real entitlement
    schema before returning non-empty here."""
    handler._respond(200, b"{}", content_type="application/x-amz-json-1.1")


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

    # Game.GetLoginInfoLists (character select payload)
    ("*", "GET", _path_prefix("/prod/game/getlogininfo"), handle_get_login_info),
    ("*", "POST", _path_prefix("/prod/game/getlogininfo"), handle_get_login_info),

    # Entitlement service (game ownership + sync flows)
    ("client.entitlementservice.amazongames.com", "POST",
     lambda p: p.endswith("/entitlements/sync"), handle_entitlements_sync),
    ("client.entitlementservice.amazongames.com", "GET",
     lambda p: p.endswith("/entitlements"), handle_entitlements_list),

    # Remote config (S3)
    ("ags-javelin-remote-config.s3.amazonaws.com", "GET", _path_prefix("/applications/"), handle_remote_config),

    # Content bundles
    ("d1hkbwzm1bktgo.cloudfront.net", "GET", _path_prefix("/motd/"), handle_worlds_motd),
    ("d1hkbwzm1bktgo.cloudfront.net", "GET", _path_prefix("/newsstories/"), handle_news_metadata),
    ("d1hkbwzm1bktgo.cloudfront.net", "GET", _path_prefix("/marketingtiles/"), handle_marketing_metadata),

    # OmniSDK token service — JWKS + OpenID config MUST match before the
    # catch-all token handler, since these are also under tokenservice.amazongames.com.
    ("tokenservice.amazongames.com", "GET", _path_endswith("/jwks.json"), handle_jwks),
    ("tokenservice.amazongames.com", "GET", _path_endswith("/openid-configuration"), handle_openid_config),
    ("tokenservice.amazongames.com", "GET", _path_endswith("/.well-known/openid-configuration"), handle_openid_config),
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
        self._last_request_body = body  # expose for handlers that need it
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
