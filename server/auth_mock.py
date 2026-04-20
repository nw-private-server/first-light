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

import atexit
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
RUN_LOGS_DIR = PROJECT_DIR / "capture" / "auth_mock_runs"
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


def _should_echo_to_terminal(msg: str) -> bool:
    return (
        msg.startswith("*** RUN ")
        or msg.startswith("[*]")
        or msg.startswith("[!]")
    )


def log(msg: str) -> None:
    with _LOG_LOCK:
        line = f"[{_ts()}] {msg}"
        if _should_echo_to_terminal(msg):
            print(line)
        try:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            (LOGS_DIR / f"{datetime.now().strftime('%Y%m%d')}.log").open("a", encoding="utf-8").write(line + "\n")
            if "*** RUN " in msg:
                RUN_LOGS_DIR.mkdir(parents=True, exist_ok=True)
                (RUN_LOGS_DIR / f"{datetime.now().strftime('%Y%m%d')}.log").open("a", encoding="utf-8").write(line + "\n")
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


def make_fake_login_ticket(
    *,
    ticket_id: str,
    persona_id: str,
    world_id: str,
    world_name: str,
    character_id: str,
    rep_host: str,
    rep_port: int,
    location: str = "",
    steam_app_id: int = 1063730,
    steam_user_id: str = "",
    token_version: int = 10,
    channel_id: str = "",
) -> dict:
    """Build a LoginQueueResponse envelope that matches the parsed schema.

    Codex/Ghidra trace 2026-04-19:
    - top-level key must be "LoginQueueResponse"
    - inner parser reads PascalCase fields including TicketId, RepAddress,
      CharacterId, PersonaId, WorldId, TokenVersion

    The old flat {ticket, worldId, repAddress, ...} object is ignored by the
    real parser and results in "No login ticket received" after queueing."""
    now = int(time.time())
    return {
        "LoginQueueResponse": {
            "AccountAge": 0,
            "AccountIsLocked": False,
            "ChannelId": channel_id,
            "CharacterId": character_id,
            "ClientCapabilities": "",
            "GenerateTime": now,
            "HostHash": "",
            "IsPermanentAppOwner": True,
            "IsTrialOwner": False,
            "IssueTime": now,
            "Location": location,
            "LocationGroupId": "",
            "LocationId": "",
            "PersonaId": persona_id,
            "RepAddress": f"{rep_host}:{rep_port}",
            # Queue-login handoff gate (FUN_14643d110 -> FUN_14114b200) compares
            # the transformed token's leading string field, which comes from
            # Signature. An empty string leaves the queue token unchanged and
            # never triggers the next-stage handoff.
            "Signature": f"sig:{ticket_id}",
            "SteamAppId": steam_app_id,
            "SteamUserId": steam_user_id,
            "TicketId": ticket_id,
            "TokenVersion": token_version,
            "WorldId": world_id,
            # Legacy convenience fields retained in case any higher-level UI
            # code still peeks at the raw JSON before the typed parser runs.
            "WorldName": world_name,
        }
    }


def make_fake_queue_refresh(
    *,
    ticket_id: str,
    persona_id: str,
    world_id: str,
    world_name: str,
    character_id: str,
    rep_host: str,
    rep_port: int,
    queue_name: str,
    steam_app_id: int = 1063730,
    steam_user_id: str = "",
    token_version: int = 10,
    channel_id: str = "",
    ready: bool = True,
    refresh_interval: int = 15,
) -> dict:
    """Build the queue-refresh envelope parsed by FUN_1474e4f20.

    The refresh path is not the same as the initial login-queue ticket parser.
    It expects queue-status fields at the top level and a nested Token object
    parsed by FUN_1474e5990.
    """
    token = make_fake_login_ticket(
        ticket_id=ticket_id,
        persona_id=persona_id,
        world_id=world_id,
        world_name=world_name,
        character_id=character_id,
        rep_host=rep_host,
        rep_port=rep_port,
        location=queue_name,
        steam_app_id=steam_app_id,
        steam_user_id=steam_user_id,
        token_version=token_version,
        channel_id=channel_id,
    )["LoginQueueResponse"]
    queue_payload = {
        "AllowQueueTransfer": False,
        "EstimatedTime": 0,
        "Position": 0 if ready else 1,
        "QueueName": queue_name,
        "RecommendedTransferWorldId": "",
        "RefreshInterval": refresh_interval,
        "TicketId": ticket_id,
        "Token": token,
    }
    return {
        "LoginQueueResponse": queue_payload,
        # Legacy fields kept for any higher-level UI code still consulting
        # the raw JSON outside the typed queue parser.
        "ticket": ticket_id,
        "worldId": world_id,
        "worldName": world_name,
        "repAddress": f"{rep_host}:{rep_port}",
        "location": queue_name,
        "status": "Granted" if ready else "Queued",
        "position": 0 if ready else 1,
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
    """Per-server session context. Tracks persona/world/character state
    across requests so create -> re-query flows stay consistent.

    The auth mock handled each request in isolation before this was added;
    codex review 2026-04-18 flagged the inconsistency as a source of
    "works on first flow, flakes on later flows" behavior. A character
    created via handle_create_character now persists in ctx.characters
    and handle_get_login_info surfaces it. Persona_id is captured from
    whichever fallbackToken.sub the OmniSDK POST carries and reused by
    every downstream handler."""

    DEFAULT_PERSONA = "amzn1.developerPersonaId.4ee4810f-da59-c553-4027-91e961054dce"
    DEFAULT_WORLD_ID = "b1a00000-0000-0000-0000-000000000002"
    DEFAULT_WORLD_NAME = "Valhalla"
    GOOD_RUN_TIMEOUT_SEC = 18.0
    POST_GETLOGININFO_TIMEOUT_SEC = 12.0
    POST_CREATE_TIMEOUT_SEC = 12.0

    def __init__(self, rep_host: str, rep_port: int, *, seed_character: bool = True):
        self.rep_host = rep_host
        self.rep_port = rep_port
        self.seed_character = seed_character
        self._lock = threading.Lock()
        self.persona_id: str = Ctx.DEFAULT_PERSONA
        self.world_id: str = Ctx.DEFAULT_WORLD_ID
        self.world_name: str = Ctx.DEFAULT_WORLD_NAME
        self.characters: list[dict] = []
        if self.seed_character:
            self.characters.append(self._build_seed_character())
        # Lightweight run-health tracker so the mock can tell us whether
        # a launch ever reached the character-select data fetch. This
        # distinguishes "bad runs" (frontend/client stall before
        # getlogininfo) from real auth-mock schema failures.
        self.run_id: int = 0
        self.run_started_at: float = 0.0
        self.run_milestones: set[str] = set()
        self.run_good_logged: bool = False
        self.run_bad_logged: bool = False
        self.run_active: bool = False
        self.run_terminal_logged: bool = False
        self.run_outcome: str | None = None
        self.run_character_select_logged: bool = False
        self.queue_tickets: dict[str, dict] = {}

    def set_persona(self, persona_id: str) -> None:
        with self._lock:
            if persona_id and persona_id != self.persona_id:
                log(f"    * ctx persona_id: {self.persona_id} -> {persona_id}")
                self.persona_id = persona_id
                for char in self.characters:
                    char["PersonaId"] = self.persona_id

    def _build_seed_character(self) -> dict:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return {
            "CharacterId": "11111111-1111-1111-1111-111111111111",
            "Name": "Existing_Dev",
            "PersonaId": self.persona_id,
            "WorldId": self.world_id,
            "CreatedDate": now,
            "ModifiedDate": now,
            "NameModifiedDate": now,
            "NameLatentDate": now,
            "NeedsTransferDate": now,
            "TransferDate": now,
            "RegionTransferDate": now,
            "LocationGroupId": "",
            "LocationId": "",
            "MustRenameReason": "",
            "OwnerState": "",
            "PublishedData": "",
            "PublishedSource": "",
            "PublishedSocialSource": "",
            "PublishedElapsedSeconds": 0,
            "PublishedSocialElapsedSeconds": 0,
            "SocialData": "",
            "TransferCrossRegionCooldownEndTime": 0,
            "TransferFreeCooldownEndTime": 0,
            "TransferData": "",
            "TransferReason": "",
            "FtueCompleted": True,
            "IsFreshStart": False,
            "IsNameLatent": False,
            "IsTrialOwner": False,
            "MustRename": False,
            "NeedsTransfer": False,
            "Transferrable": False,
        }

    def add_character(self, entry: dict) -> None:
        with self._lock:
            self.characters.append(entry)
            log(f"    * ctx characters: {len(self.characters)} total")

    def snapshot_characters(self) -> list[dict]:
        with self._lock:
            return list(self.characters)

    def issue_queue_ticket(
        self,
        *,
        character_id: str,
        steam_app_id: int,
        token_version: int,
        channel_id: str,
    ) -> dict:
        with self._lock:
            ticket_id = str(uuid.uuid4())
            ticket = {
                "TicketId": ticket_id,
                "CharacterId": character_id,
                "SteamAppId": steam_app_id,
                "TokenVersion": token_version,
                "ChannelId": channel_id,
                "RefreshCount": 0,
                # Gate 2 objective is to reach REP/DTLS, not to model a real
                # waiting queue. The queue UI path is flaky, so issue a
                # connectable ticket immediately and let refreshes maintain it.
                "Ready": True,
                # QueueName is mapped through the client's built-in
                # @mm_loginservices_location_ lookup table. "pdx-prod" parses
                # but resolves to an empty display string; the AWS region token
                # is the more likely valid identifier for US West.
                "QueueName": "us-west-2",
                "LocationGroupId": "pdx-prod",
                "LocationId": self.world_id,
            }
            self.queue_tickets[ticket_id] = ticket
            return dict(ticket)

    def refresh_queue_ticket(self, ticket_id: str) -> dict | None:
        with self._lock:
            ticket = self.queue_tickets.get(ticket_id)
            if ticket is None:
                return None
            ticket["RefreshCount"] += 1
            ticket["Ready"] = True
            ticket["QueueName"] = "us-west-2"
            ticket["LocationGroupId"] = "pdx-prod"
            ticket["LocationId"] = self.world_id
            return dict(ticket)

    def mark_run_event(self, event: str) -> None:
        """Track high-level launch milestones and classify runs.

        "Good run" means the client reached /getlogininfo at all.
        "Bad run" means auth completed but the frontend stalled before
        requesting /getlogininfo (the flaky pre-character-select issue)."""
        timer_snapshot = None
        with self._lock:
            if event == "credentials_omni":
                self.run_id += 1
                self.run_started_at = time.monotonic()
                self.run_milestones = {event}
                self.run_good_logged = False
                self.run_bad_logged = False
                self.run_active = True
                self.run_terminal_logged = False
                self.run_outcome = None
                self.run_character_select_logged = False
                timer_snapshot = self.run_id
                log(
                    f"*** RUN {self.run_id}: started at /credentials/omni "
                    f"(waiting for /getlogininfo)"
                )
            elif not self.run_active:
                return
            else:
                self.run_milestones.add(event)

            if event == "entitlements_sync":
                log(f"*** RUN {self.run_id}: gate progress -> entitlements/sync")
            elif event == "entitlements":
                log(f"*** RUN {self.run_id}: gate progress -> entitlements")
            elif event == "getlogininfo" and not self.run_good_logged:
                self.run_good_logged = True
                elapsed = time.monotonic() - self.run_started_at
                log(
                    f"*** RUN {self.run_id}: GOOD RUN "
                    f"(reached /getlogininfo after {elapsed:.1f}s)"
                )
                t = threading.Thread(
                    target=self._post_getlogininfo_watchdog,
                    args=(self.run_id,),
                    daemon=True,
                )
                t.start()
            elif event == "validate_character":
                log(f"*** RUN {self.run_id}: gate progress -> validator")
            elif event == "create_character":
                log(f"*** RUN {self.run_id}: gate progress -> create character")
                t = threading.Thread(
                    target=self._post_create_watchdog,
                    args=(self.run_id,),
                    daemon=True,
                )
                t.start()
            elif event == "login_queue_v2":
                log(f"*** RUN {self.run_id}: gate progress -> login/queue/v2")
                self._finalize_run_locked(
                    "REACHED_LOGIN_QUEUE_V2",
                    "passed character-select/create and reached the REP handoff gate",
                )

        if timer_snapshot is not None:
            t = threading.Thread(
                target=self._bad_run_watchdog,
                args=(timer_snapshot,),
                daemon=True,
            )
            t.start()

    def _bad_run_watchdog(self, run_id: int) -> None:
        time.sleep(Ctx.GOOD_RUN_TIMEOUT_SEC)
        with self._lock:
            if (
                not self.run_active
                or self.run_id != run_id
                or self.run_good_logged
                or self.run_bad_logged
                or self.run_terminal_logged
            ):
                return
            # Only call it a bad run once auth genuinely advanced.
            enough_progress = (
                "credentials_omni" in self.run_milestones
                and "entitlements" in self.run_milestones
            )
            if not enough_progress:
                return
            self.run_bad_logged = True
            elapsed = time.monotonic() - self.run_started_at
            self._finalize_run_locked(
                "BAD_PRE_GETLOGININFO",
                f"still no /getlogininfo after {elapsed:.1f}s; "
                f"frontend/state-machine stall, not REP/DTLS",
            )

    def _post_getlogininfo_watchdog(self, run_id: int) -> None:
        time.sleep(Ctx.POST_GETLOGININFO_TIMEOUT_SEC)
        with self._lock:
            if (
                not self.run_active
                or self.run_id != run_id
                or self.run_terminal_logged
            ):
                return
            if "getlogininfo" not in self.run_milestones:
                return
            if any(
                milestone in self.run_milestones
                for milestone in ("validate_character", "create_character", "login_queue_v2")
            ):
                return
            if self.seed_character:
                if not self.run_character_select_logged:
                    elapsed = time.monotonic() - self.run_started_at
                    self.run_character_select_logged = True
                    log(
                        f"*** RUN {self.run_id}: AT_CHARACTER_SELECT "
                        f"(seeded-character path; no validator/create yet after {elapsed:.1f}s)"
                    )
                return
            elapsed = time.monotonic() - self.run_started_at
            self._finalize_run_locked(
                "GETLOGININFO_THEN_CTD_OR_STALL",
                f"reached /getlogininfo but never advanced to validator/create "
                f"after {elapsed:.1f}s",
            )

    def _post_create_watchdog(self, run_id: int) -> None:
        time.sleep(Ctx.POST_CREATE_TIMEOUT_SEC)
        with self._lock:
            if (
                not self.run_active
                or self.run_id != run_id
                or self.run_terminal_logged
            ):
                return
            if "create_character" not in self.run_milestones:
                return
            if "login_queue_v2" in self.run_milestones:
                return
            elapsed = time.monotonic() - self.run_started_at
            self._finalize_run_locked(
                "CREATE_THEN_NO_LOGIN_QUEUE",
                f"created a character but never reached /login/queue/v2 "
                f"after {elapsed:.1f}s",
            )

    def _finalize_run_locked(self, outcome: str, detail: str) -> None:
        self.run_terminal_logged = True
        self.run_active = False
        self.run_outcome = outcome
        log(f"*** RUN {self.run_id}: OUTCOME {outcome} ({detail})")

    def emit_shutdown_summary(self) -> None:
        with self._lock:
            if self.run_id == 0:
                return
            if self.run_terminal_logged:
                return
            milestones = ",".join(sorted(self.run_milestones)) if self.run_milestones else "none"
            elapsed = 0.0
            if self.run_started_at:
                elapsed = time.monotonic() - self.run_started_at
            self._finalize_run_locked(
                "ABORTED_WITHOUT_TERMINAL_OUTCOME",
                f"auth_mock stopped after {elapsed:.1f}s; milestones={milestones}",
            )


def handle_channel_service(ctx: Ctx, handler: "AuthHandler"):
    body = json.dumps(build_channel_config(ctx.rep_host, ctx.rep_port)).encode()
    handler._respond(200, body, content_type="application/json")


def handle_credentials_omni(ctx: Ctx, handler: "AuthHandler"):
    """Schema confirmed from FUN_145a955e0 (SteamAuth response handler).
    The parser reads four FLAT top-level fields off the document — no
    gatewayCredentials/personaCredentials wrapper. Offsets in the resulting
    credentials object: accessKeyId @ 0x10, secretAccessKey @ 0x30,
    sessionToken @ 0x50, expiration parsed into a chrono::time_point @ 0x70."""
    ctx.mark_run_event("credentials_omni")
    body = json.dumps(make_fake_credentials("omni")).encode()
    handler._respond(200, body, content_type="application/json")


def handle_login_queue(ctx: Ctx, handler: "AuthHandler"):
    if handler.path.startswith("/prod/game/login/queue"):
        ctx.mark_run_event("login_queue_v2")
    request = {}
    try:
        request = json.loads(handler._last_request_body or b"{}").get("LoginQueueRequest", {})
    except Exception as e:
        log(f"    * failed to parse LoginQueueRequest: {e}")

    query = urlparse(handler.path).query
    channel_id = ""
    token_version = 10
    if query:
        for kv in query.split("&"):
            if "=" not in kv:
                continue
            key, value = kv.split("=", 1)
            if key == "channelId":
                channel_id = value
            elif key == "tokenVersion":
                try:
                    token_version = int(value)
                except ValueError:
                    pass

    character_id = request.get("CharacterId") or (
        ctx.snapshot_characters()[-1]["CharacterId"] if ctx.snapshot_characters() else ""
    )
    requested_world_id = request.get("WorldId") or ""
    if requested_world_id and requested_world_id != ctx.world_id:
        log(f"    * queue login requested world override: {requested_world_id}")
    steam_app_id = int(request.get("SteamAppId") or 1063730)
    # SteamUserId is not currently available from our mock auth path. The
    # parser accepts an empty string, which is safer than inventing a random
    # value that drifts across requests.
    steam_user_id = ""

    parsed = urlparse(handler.path)
    path_parts = [part for part in parsed.path.split("/") if part]
    refresh_ticket_id = ""
    if (
        len(path_parts) >= 8
        and path_parts[:5] == ["prod", "game", "login", "queue", "v2"]
        and path_parts[6] == "jwt"
    ):
        refresh_ticket_id = path_parts[5]

    if refresh_ticket_id:
        ticket_state = ctx.refresh_queue_ticket(refresh_ticket_id)
        if ticket_state is None:
            log(f"    * unknown queue ticket refresh: {refresh_ticket_id}")
            ticket_state = ctx.issue_queue_ticket(
                character_id=character_id,
                steam_app_id=steam_app_id,
                token_version=token_version,
                channel_id=channel_id,
            )
        else:
            log(
                "    * queue ticket refresh: "
                f"id={refresh_ticket_id} count={ticket_state['RefreshCount']} "
                f"ready={ticket_state['Ready']} "
                f"location=({ticket_state['LocationGroupId']},{ticket_state['LocationId']})"
            )
        response = make_fake_queue_refresh(
            ticket_id=ticket_state["TicketId"],
            persona_id=ctx.persona_id,
            world_id=ctx.world_id,
            world_name=ctx.world_name,
            character_id=ticket_state["CharacterId"],
            rep_host=ctx.rep_host,
            rep_port=ctx.rep_port,
            queue_name=ticket_state.get("QueueName") or "us-west-2",
            steam_app_id=ticket_state["SteamAppId"],
            steam_user_id=steam_user_id,
            token_version=ticket_state["TokenVersion"],
            channel_id=ticket_state["ChannelId"],
            ready=ticket_state["Ready"],
            refresh_interval=15,
        )
    else:
        ticket_state = ctx.issue_queue_ticket(
            character_id=character_id,
            steam_app_id=steam_app_id,
            token_version=token_version,
            channel_id=channel_id,
        )
        log(
            "    * issued queue ticket: "
            f"id={ticket_state['TicketId']} channel={channel_id or '<empty>'} "
            f"character={character_id}"
        )
        response = make_fake_queue_refresh(
            ticket_id=ticket_state["TicketId"],
            persona_id=ctx.persona_id,
            world_id=ctx.world_id,
            world_name=ctx.world_name,
            character_id=ticket_state["CharacterId"],
            rep_host=ctx.rep_host,
            rep_port=ctx.rep_port,
            queue_name=ticket_state.get("QueueName") or "us-west-2",
            steam_app_id=ticket_state["SteamAppId"],
            steam_user_id=steam_user_id,
            token_version=ticket_state["TokenVersion"],
            channel_id=ticket_state["ChannelId"],
            ready=ticket_state["Ready"],
            refresh_interval=15,
        )
        # Keep the older convenience fields inside the same envelope too.
        response["LoginQueueResponse"]["QueueReady"] = ticket_state["Ready"]
        response["LoginQueueResponse"]["Status"] = "Granted" if ticket_state["Ready"] else "Queued"
        response["LoginQueueResponse"]["Location"] = ticket_state.get("QueueName") or "us-west-2"
        response["LoginQueueResponse"]["QueuePosition"] = 0 if ticket_state["Ready"] else 1

    body = json.dumps(response).encode()
    handler._respond(200, body, content_type="application/json")


def handle_get_login_info(ctx: Ctx, handler: "AuthHandler"):
    """GET /prod/game/getlogininfo/jwt/omni?channelId=...&includeNames=true

    Two schemas in one response body, both verified from the binary:

    - lowercase `worlds`/`recommendedWorlds` feed the UI dropdown via the
      RPC schema table in FUN_144f40780 (WorldMetadata -- int enums).
    - capital `LoginInfoList.Worlds` + `LoginInfoList.Characters` feed
      the create-character gate via FUN_1474e42e0 (PascalCase fields,
      string enums). WorldStatus="ACTIVE" + WorldType="OpenWorld" +
      PublicStatusCode=0 is the Codex-verified combo that makes a world
      pass FUN_1464460d0 and FUN_146423730.

    Uses ctx.persona_id / ctx.world_id / ctx.characters so the response
    stays consistent with anything the create/validate handlers persisted."""
    ctx.mark_run_event("getlogininfo")
    world_id = ctx.world_id
    world_name = ctx.world_name
    characters = ctx.snapshot_characters()

    world_metrics = {
        "worldAgeDays": 1,
        "queueSize": 0,
        "queueWaitTimeSec": 0,
        "worldPopulationStatus": 1,
    }
    # NOTE: lowercase WorldMetadata and PascalCase LoginInfoList.Worlds are
    # separate client models with slightly different consumers. Keep every
    # shared field aligned and only allow the one currently necessary
    # divergence: lowercase publicStatusCode=1 remains the stable render
    # value, while PascalCase PublicStatusCode=0 is what the ACTIVE-world
    # candidate gate currently accepts.
    world_common = {
        "publicName": world_name,
        "version": "1.0.0",
        "maxAccountCharacters": 10,
        "worldSet": "live",
        "transferToRegion": "",
        "isFull": False,
        "isRecommended": True,
    }
    # Lowercase WorldMetadata for the dropdown consumer.
    world = {
        "worldId": world_id,
        "type": 1,
        "status": 1,
        "publicStatusCode": 1,
        "worldMetrics": dict(world_metrics),
        **world_common,
    }

    # PascalCase world for the create-character gate. Per Codex trace
    # (FUN_146427100): candidate+0x58 <- WorldStatus, +0x50 <- WorldType
    # (via FUN_1417c40a0 where only literal "OpenWorld" maps to 1),
    # +0x80 <- PublicStatusCode (must pass (x & 0xffffe8b7) == 0).
    world_capital = {
        "WorldId": world_id,
        "WorldName": world_name,
        "PublicName": world_common["publicName"],
        "WorldStatus": "ACTIVE",
        "WorldType": "OpenWorld",
        "WorldSet": world_common["worldSet"],
        "WorldVersion": world_common["version"],
        "PublicStatusCode": 0,
        "MaxAccountCharacters": world_common["maxAccountCharacters"],
        "MaxConnectionCount": 1000,
        "ConnectionCount": 0,
        "IsFull": world_common["isFull"],
        "IsRecommended": world_common["isRecommended"],
        "TransferToRegion": world_common["transferToRegion"],
        "WorldMetrics": {
            "WorldAgeDays": world_metrics["worldAgeDays"],
            "QueueSize": world_metrics["queueSize"],
            "QueueWaitTimeSec": world_metrics["queueWaitTimeSec"],
            "WorldPopulationStatus": world_metrics["worldPopulationStatus"],
        },
    }

    # Codex FUN_1474e01e0 decompile: parser ONLY reads top-level
    # "LoginInfoList" key and then recurses into that sub-document with
    # FUN_1474e42e0 (which reads Characters/Worlds/etc). Without the
    # envelope, the embedded parse block is zeroed, which trips the
    # apply-side status check downstream and blocks the candidate vector
    # from reaching GameConnection+0x14e8.
    #
    body = json.dumps({
        "worlds": [world],
        "recommendedWorlds": [],
        "LoginInfoList": {
            "Worlds": [world_capital],
            "Characters": characters,
            "MaxChannelCharacters": 10,
            "CrossRegionTransferCooldownMins": 0,
            "NameReservations": [],
            "PendingWorldMerges": [],
        },
    }).encode()
    handler._respond(200, body, content_type="application/json")


def handle_validate_character(ctx: Ctx, handler: "AuthHandler"):
    """POST /prod/game/worlds/{worldId}/characters/validator/jwt/omni

    Body: {"ValidateCharacterBody":{"Name":"..."}}

    Returns validation result. Real server checks name availability +
    content policy. We just mark any name available."""
    ctx.mark_run_event("validate_character")
    body = json.dumps({
        "ValidateCharacterResult": {
            "IsAvailable": True,
            "IsValid": True,
        },
    }).encode()
    handler._respond(200, body, content_type="application/json")


def handle_create_character(ctx: Ctx, handler: "AuthHandler"):
    """POST /prod/game/worlds/{worldId}/characters/jwt/omni

    Body: {"CreateCharacterRequest":{"CharacterCreationParams":"<base64 zlib-compressed protobuf>"}}

    After this, the game tries to connect to the REP server at the
    address in the login ticket (127.0.0.1:23971 in our mock) for
    gameplay. That's gate 2 (DTLS/Javelin) work.

    Persist the character in ctx so a subsequent getlogininfo surfaces
    it in LoginInfoList.Characters[]. Without persistence the client
    thinks it created a character but the next login_info refresh says
    "no characters" -- the inconsistency fouls up the next flow."""
    ctx.mark_run_event("create_character")
    character_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # Best-effort name extraction from the request body -- the body has
    # the character name embedded (after a ValidateCharacter round-trip).
    # If we can't parse it cleanly, fall back to a synthetic name.
    name = f"Dev_{character_id[:8]}"
    try:
        parsed = json.loads(handler._last_request_body or b"{}")
        # CharacterCreationParams is base64 zlib protobuf; we don't
        # decode it yet. Task #28 covers that. For now the name isn't
        # critical -- the client has it locally.
        del parsed
    except Exception:
        pass
    ctx.add_character({
        "CharacterId": character_id,
        "Name": name,
        "PersonaId": ctx.persona_id,
        "WorldId": ctx.world_id,
        "CreatedDate": now,
        "ModifiedDate": now,
        "NameModifiedDate": now,
        "NameLatentDate": now,
        "NeedsTransferDate": now,
        "TransferDate": now,
        "RegionTransferDate": now,
        "LocationGroupId": "",
        "LocationId": "",
        "MustRenameReason": "",
        "OwnerState": "",
        "PublishedData": "",
        "PublishedSource": "",
        "PublishedSocialSource": "",
        "PublishedElapsedSeconds": 0,
        "PublishedSocialElapsedSeconds": 0,
        "SocialData": "",
        "TransferCrossRegionCooldownEndTime": 0,
        "TransferFreeCooldownEndTime": 0,
        "TransferData": "",
        "TransferReason": "",
        "FtueCompleted": True,
        "IsFreshStart": True,
        "IsNameLatent": False,
        "IsTrialOwner": False,
        "MustRename": False,
        "NeedsTransfer": False,
        "Transferrable": False,
    })
    # Codex trace 2026-04-19 (revised): the REST /characters/jwt/omni
    # success parser is FUN_1474e1090. It looks for a top-level
    # "Character" key (NOT "CreateCharacterResult") and hands the
    # sub-document to FUN_1474e1f60 -- the same PascalCase
    # CharacterMetadata parser used for LoginInfoList.Characters[].
    # Return the full character record we just persisted; the client
    # uses this directly, and the next gate is /game/login/queue/v2.
    character_record = ctx.characters[-1] if ctx.characters else {
        "CharacterId": character_id,
        "Name": name,
        "PersonaId": ctx.persona_id,
        "WorldId": ctx.world_id,
    }
    body = json.dumps({"Character": character_record}).encode()
    handler._respond(200, body, content_type="application/json")


def handle_remote_config(ctx: Ctx, handler: "AuthHandler"):
    """S3 ags-javelin-remote-config: returns minimal config blobs.

    Path shape:
      /applications/<scope>/configuration-sets/<dimension>/<id>/<version>
    Known scopes: public, publicGameplay.
    Known dimensions: ProductId, RegionId, CognitoId.

    Per-region character slot cap lives in key
    `UIFeatures.landingScreenForceMaxCharacters` (Codex trace 2026-04-18:
    FUN_144a39790 registers the key with default 0; FUN_1441f1400 registers
    the script-facing getter `Game.GetMaximumCharactersPerRegion`). Codex
    fingered `remoteCfg.public.RegionId` as the most likely layer — return
    the override there. Everything else stays `{}`."""
    parts = handler.path.lstrip("/").split("/")
    if len(parts) >= 5 and parts[0] == "applications" and parts[2] == "configuration-sets":
        scope, dimension, ident = parts[1], parts[3], parts[4]
        log(f"    * remote-config scope={scope} dimension={dimension} id={ident}")
        if scope == "public" and dimension == "RegionId":
            body = json.dumps({
                "UIFeatures.landingScreenForceMaxCharacters": 4,
            }).encode()
            handler._respond(200, body, content_type="application/json")
            return
    handler._respond(200, b"{}", content_type="application/json")


def handle_worlds_motd(ctx: Ctx, handler: "AuthHandler"):
    """MOTD / worlds_<channel>.json.

    Populating either `worldSets[]` or `worlds[]` with guessed entries
    causes a CTD -- the real schema for MOTD world entries is unknown.
    Keep minimal stable shape. The "ACTIVE" string check Codex found
    on the world-public-status model is sourced from a DIFFERENT feed
    -- location still unidentified. Next hunt: find what URL/endpoint
    provides that world-public-status data."""
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
    persona_id = ctx.persona_id
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
    # Commit the persona_id we're using into the session so every other
    # handler (credentials, entitlements, getlogininfo, create-character)
    # reuses the same value. Codex review flagged mismatched persona_id
    # across handlers as a high-severity flakiness vector.
    ctx.set_persona(persona_id)

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

    URL-first trace confirmed this endpoint has NO JSON response parser.
    URL builder FUN_1474d5100 handles success/failure inline against HTTP
    status — zero JSON fields are read from the response body. The request
    writer FUN_1474d4d60 emits {syncTypes[...] + optional entitledPersonaId/
    event/platformSyncParameters}, but the response body is ignored on
    success. {} is the intended stub shape."""
    ctx.mark_run_event("entitlements_sync")
    handler._respond(200, b"{}", content_type="application/x-amz-json-1.1")


def handle_entitlements_list(ctx: Ctx, handler: "AuthHandler"):
    """GET /players/{personaId}/games/new-world/platforms/steam/entitlements

    Schema confirmed via URL-first Ghidra trace (2026-04-18):
      FUN_1474caa10 builds the URL.
      FUN_1474c2420 is the top-level response parser.
      FUN_1474bde20 -> FUN_1474c4630 handle each lineItems entry.

    Response is a generic paginated list: {hasMoreResults, lineItems[]}.
    NOT {entitlements: [...], status: "..."} — that wrapper was invented
    and explains every non-{} CTD we've hit on this endpoint.

    Per-entry fields (all strings except `amount` which is numeric):
      acquisitionPersonaId, acquisitionType, amount, createdDate,
      productId, transactionId, type."""
    ctx.mark_run_event("entitlements")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = json.dumps({
        "hasMoreResults": False,
        "lineItems": [
            {
                "acquisitionPersonaId": ctx.persona_id,
                "acquisitionType": "Grant",
                "amount": 1,
                "createdDate": now,
                "productId": "STEAM_APP_ID.1063730",
                "transactionId": "nwprivate-base-game",
                "type": "BaseGame",
            },
        ],
    }).encode()
    handler._respond(200, body, content_type="application/x-amz-json-1.1")


def handle_javelin_rpc(ctx: Ctx, handler: "AuthHandler"):
    """Preemptive logger for /Javelin.RPC.<Service>/<Method> gRPC-style paths.

    We've traced CreateCharacter (and siblings GetLoginInfo, ValidateCharacter,
    GetCharacterList) to `ControlPortClient<StubbedGatewayService>`, which
    sends to paths like `/Javelin.RPC.StubbedGatewayService/<Method>`. The
    transport is HTTP/gRPC through the same gateway we're already mocking,
    but the wire format (real HTTP/2 + protobuf frames? or HTTP/1.1 with a
    protobuf body?) is not yet confirmed. Respond with empty {} on HTTP/1.1
    so we at least capture the request — if the client actually needs real
    gRPC framing this call will fail at the protocol layer before we see it."""
    body = handler._last_request_body or b""
    ct = handler.headers.get("Content-Type", "")
    log(f"    ! JAVELIN-RPC path={handler.path} content-type={ct} body={len(body)}B")
    if body:
        hex_head = body[:128].hex()
        log(f"    ! JAVELIN-RPC body-hex[0:128]: {hex_head}")
    handler._respond(200, b"{}", content_type="application/json")


def handle_unknown(ctx: Ctx, handler: "AuthHandler"):
    """Catch-all: return an empty JSON object so the client doesn't crash.
    The goal here is to KEEP the client progressing so we can see what it
    asks for next. High-value hosts (tokenservice, entitlementservice,
    gateway CloudFront) are noisy in the log via `! no route matched` so
    schema drift on those paths stands out."""
    handler._respond(200, b"{}", content_type="application/json")


# Routes are matched in order. First match wins.
ROUTES = [
    # Channel service
    ("d2c74t4zimux3r.cloudfront.net", "GET", _path_endswith(".json"), handle_channel_service),

    # Credentials (omni)
    ("*", "POST", _path_endswith("/credentials/omni"), handle_credentials_omni),
    ("*", "GET", _path_endswith("/credentials/omni"), handle_credentials_omni),

    # Login queue. The real path under FUN_146417490 is
    # /prod/game/login/queue/v2[/jwt[/omni]] (Codex trace 2026-04-19).
    # Kept the older /prod/users/login_queue prefix match for earlier
    # builds / alternate code paths.
    ("*", "POST", _path_prefix("/prod/game/login/queue"), handle_login_queue),
    ("*", "GET", _path_prefix("/prod/game/login/queue"), handle_login_queue),
    ("*", "POST", _path_prefix("/prod/users/login_queue"), handle_login_queue),
    ("*", "GET", _path_prefix("/prod/users/login_queue"), handle_login_queue),

    # Game.GetLoginInfoLists (character select payload)
    ("*", "GET", _path_prefix("/prod/game/getlogininfo"), handle_get_login_info),
    ("*", "POST", _path_prefix("/prod/game/getlogininfo"), handle_get_login_info),

    # ValidateCharacter + CreateCharacter (REST endpoints, not the gRPC
    # path Codex originally suggested). Paths observed live in auth-mock
    # logs: /prod/game/worlds/<worldId>/characters/validator/jwt/omni
    # and /prod/game/worlds/<worldId>/characters/jwt/omni.
    ("*", "POST",
     lambda p: "/prod/game/worlds/" in p and "/characters/validator" in p,
     handle_validate_character),
    ("*", "POST",
     lambda p: "/prod/game/worlds/" in p and p.split("?")[0].endswith("/characters/jwt/omni"),
     handle_create_character),

    # gRPC-style ControlPort RPCs (CreateCharacter, ValidateCharacter,
    # GetCharacterList, GetLoginInfo, ...). Preemptive logger — wire
    # format not confirmed yet; returning {} so we at least capture the
    # request body for analysis.
    ("*", "POST", _path_prefix("/Javelin.RPC."), handle_javelin_rpc),
    ("*", "GET", _path_prefix("/Javelin.RPC."), handle_javelin_rpc),

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

        log(f"    !!! NO-ROUTE {self.command} https://{host}{self.path}  body={len(body)}B")
        if body:
            log(f"    !!! NO-ROUTE body-hex[0:128]: {body[:128].hex()}")
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
    ap.add_argument(
        "--no-seed-character",
        action="store_true",
        help="Disable the default Existing_Dev seeded character and test the empty-character path",
    )
    args = ap.parse_args()

    cert = Path(args.cert)
    key = Path(args.key)
    if not cert.exists() or not key.exists():
        print("[!] Missing HTTPS cert/key.")
        print(f"    Expected: {cert}")
        print(f"    Expected: {key}")
        print("    Run: python tools/generate_auth_certs.py")
        sys.exit(1)

    ctx = Ctx(args.rep_host, args.rep_port, seed_character=not args.no_seed_character)
    atexit.register(ctx.emit_shutdown_summary)
    ssl_ctx = build_ssl_context(cert, key)

    if ctx.seed_character:
        seeded = ctx.snapshot_characters()[0]
        log(
            "[*] seeded-character mode enabled: "
            f"{seeded['Name']} ({seeded['CharacterId']}) "
            f"persona={seeded['PersonaId']} world={seeded['WorldId']}"
        )
    else:
        log("[*] seeded-character mode disabled: testing empty-character path")

    server = ThreadedHTTPSServer((args.host, args.port), AuthHandler, ctx, ssl_ctx)

    log("[*] HTTPS auth mock starting")
    log(f"    Bind:    {args.host}:{args.port}")
    log(f"    Cert:    {cert}")
    log(f"    REP:     {args.rep_host}:{args.rep_port}  (returned in login tickets)")
    log("    Logs:    " + str(LOGS_DIR))
    log("    Run log: " + str(RUN_LOGS_DIR))
    log("")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("[*] stopping.")
    finally:
        ctx.emit_shutdown_summary()
        server.server_close()


if __name__ == "__main__":
    main()
