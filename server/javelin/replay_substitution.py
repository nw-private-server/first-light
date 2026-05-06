"""Replay-substitution: fill redacted spans in captured replay messages with
live-session values.

Consumes ReplayMessage instances from `replay_store` and produces fresh body
bytes with the captured XX placeholders replaced by values derived from the
live V3 RegistrationRequest. Length-preserving by construction.

See `analysis/replay_substitution_design.md` for the full design rationale.

Span-length conventions (the captured dump groups all redactions into a small
set of length classes):

    8   AzCore-CRC-shaped hash. Zero-filled for v1 (see design risk #1).
    16  Raw-binary UUID (session / persona / character).
    18, 19, 20  Length-prefixed character display name.
    36  Dashed-text UUID.
    61  Persona-id text "amzn1.developerPersonaId.<uuid>".
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from typing import Optional

from server.javelin.replay_store import ReplayMessage
from server.javelin.v3_request import V3RegistrationRequest


_DEFAULT_DISPLAY_NAME = "NWPrivateTester01"


def _persona_uuid_text_from_persona_id(persona_id: str) -> str:
    """Extract the trailing 36-char dashed UUID from `amzn1.developerPersonaId.<uuid>`.

    Returns "" if the input doesn't have the expected shape.
    """
    if len(persona_id) < 36:
        return ""
    candidate = persona_id[-36:]
    try:
        parsed = uuid.UUID(candidate)
    except ValueError:
        return ""
    return str(parsed)


def _uuid_text_to_bytes(text: str) -> bytes:
    """Convert a 36-char dashed UUID to 16 raw bytes, or b'' on parse failure."""
    try:
        return uuid.UUID(text).bytes
    except (ValueError, AttributeError):
        return b""


def _stub_character_uuid_from_persona(persona_id: str) -> uuid.UUID:
    """Deterministic UUID5 derived from persona_id.

    Per the design doc, character-UUID has no live source from V3 alone.
    This stub keeps replay deterministic without leaking real character IDs.
    """
    namespace = uuid.UUID("00000000-0000-0000-0000-000000000001")
    return uuid.uuid5(namespace, persona_id or "anonymous")


def _pad_or_truncate(text: str, target_len: int) -> bytes:
    """ASCII-encode `text`, then pad with '0' or truncate to exactly `target_len` bytes."""
    raw = text.encode("ascii", errors="replace")
    if len(raw) > target_len:
        return raw[:target_len]
    return raw + b"0" * (target_len - len(raw))


# (seq, span_length) -> field-name override.
#
# Most spans match by length alone. This table handles the cases where the
# default length-only dispatch would pick the wrong field (e.g. a 16-byte
# span that's actually a character UUID, not a persona UUID). Start coarse;
# refine as the live test loop reveals mismatches.
SPAN_RULES: dict[tuple[int, int], str] = {
    # No overrides yet — empty dispatch table means everything falls through
    # to the length-keyed default below. Add entries here as the test loop
    # reveals which seq+length combos need a different field.
}


# Fallback: dispatch by length alone when (seq, length) isn't in SPAN_RULES.
LENGTH_DEFAULT: dict[int, str] = {
    8:  "azcore_hash",
    16: "persona_uuid_bytes",
    18: "display_name_18",
    19: "display_name_19",
    20: "display_name_20",
    36: "session_uuid_text",
    61: "persona_id_text",
}


@dataclass(frozen=True)
class SubstitutionContext:
    """Live-session values used to fill redacted replay-message spans.

    Built once per session right after the V3 RegistrationRequest is parsed.
    Immutable thereafter so multiple replay sends use a consistent identity.
    """

    # --- Identity (high-confidence — sourced from V3 request) ---
    persona_id_text: str
    persona_uuid_bytes: bytes
    persona_uuid_text: str
    session_uuid_bytes: bytes
    session_uuid_text: str
    session_token: bytes

    # --- Identity (low-confidence — deterministic stubs) ---
    character_uuid_bytes: bytes
    character_uuid_text: str
    character_display_name: str

    # Diagnostics: every span we handled with a fallback / heuristic gets
    # logged here so the caller can review and feed back into SPAN_RULES.
    warnings: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    @classmethod
    def from_v3_and_session(
        cls,
        *,
        req: V3RegistrationRequest,
        session_token: bytes,
        character_display_name: str = _DEFAULT_DISPLAY_NAME,
        auth_state: Optional[dict] = None,
    ) -> "SubstitutionContext":
        """Build a context from a parsed V3 request + session response token.

        `auth_state` is reserved for a future bridge to the auth-mock state
        (so we can pull a real character_id once the responder shares state
        with the HTTPS mock). Pass None for now — character-UUID falls back
        to a deterministic stub.
        """
        warnings: list[str] = []

        persona_id_text = req.persona_id or ""
        if not persona_id_text:
            warnings.append("persona_id missing from V3 request — using empty stub")

        persona_uuid_text = _persona_uuid_text_from_persona_id(persona_id_text)
        persona_uuid_bytes = _uuid_text_to_bytes(persona_uuid_text)
        if not persona_uuid_bytes:
            warnings.append("persona UUID could not be derived from persona_id")

        session_uuid_text = req.session_uuid or ""
        session_uuid_bytes = _uuid_text_to_bytes(session_uuid_text)
        if not session_uuid_bytes:
            warnings.append("session UUID could not be parsed from V3 request")

        # Character UUID: stub from persona unless caller provided auth_state
        # with a real value (forward-compat hook).
        if auth_state and isinstance(auth_state.get("character_uuid"), uuid.UUID):
            character_uuid = auth_state["character_uuid"]
        else:
            character_uuid = _stub_character_uuid_from_persona(persona_id_text)
            warnings.append(
                "character UUID stubbed from persona-id "
                "(no auth-state bridge available)"
            )

        return cls(
            persona_id_text=persona_id_text,
            persona_uuid_bytes=persona_uuid_bytes,
            persona_uuid_text=persona_uuid_text,
            session_uuid_bytes=session_uuid_bytes,
            session_uuid_text=session_uuid_text,
            session_token=session_token,
            character_uuid_bytes=character_uuid.bytes,
            character_uuid_text=str(character_uuid),
            character_display_name=character_display_name,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------
    def apply(self, msg: ReplayMessage) -> bytes:
        """Substitute every redacted span in `msg.body` and return new bytes.

        Length-preserving: `len(returned) == len(msg.body)` always.
        Spans whose length we don't recognize get their original zero-fill
        and append a warning to `self.warnings`.
        """
        if not msg.has_redaction:
            return msg.body

        out = bytearray(msg.body)
        for offset, length in msg.redacted_spans:
            field_name = SPAN_RULES.get((msg.seq, length)) or LENGTH_DEFAULT.get(length)
            if field_name is None:
                self.warnings.append(
                    f"seq=0x{msg.seq:x} off=0x{offset:x} len={length}: "
                    f"no rule, leaving zero-filled"
                )
                continue
            replacement = self._field_bytes(field_name, length)
            if len(replacement) != length:
                self.warnings.append(
                    f"seq=0x{msg.seq:x} off=0x{offset:x} len={length} "
                    f"field={field_name}: replacement was len={len(replacement)}, "
                    f"truncating/padding to fit"
                )
                replacement = self._fit(replacement, length)
            out[offset:offset + length] = replacement

        return bytes(out)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _field_bytes(self, field_name: str, length: int) -> bytes:
        if field_name == "persona_uuid_bytes":
            return self.persona_uuid_bytes or b"\x00" * length
        if field_name == "session_uuid_bytes":
            return self.session_uuid_bytes or b"\x00" * length
        if field_name == "character_uuid_bytes":
            return self.character_uuid_bytes
        if field_name == "session_uuid_text":
            return self.session_uuid_text.encode("ascii") if self.session_uuid_text \
                else b"\x00" * length
        if field_name == "persona_uuid_text":
            return self.persona_uuid_text.encode("ascii") if self.persona_uuid_text \
                else b"\x00" * length
        if field_name == "character_uuid_text":
            return self.character_uuid_text.encode("ascii")
        if field_name == "persona_id_text":
            return self.persona_id_text.encode("ascii") if self.persona_id_text \
                else b"\x00" * length
        if field_name == "session_token":
            return self.session_token
        if field_name == "azcore_hash":
            # Per design doc risk #1: zero-fill is the v1 strategy.
            # If the client validates the hash we'll need to port AZ_CRC.
            return b"\x00" * length
        if field_name.startswith("display_name_"):
            return _pad_or_truncate(self.character_display_name, length)
        # Unknown field name reached SPAN_RULES somehow. Treat as zero-fill.
        return b"\x00" * length

    @staticmethod
    def _fit(data: bytes, length: int) -> bytes:
        if len(data) > length:
            return data[:length]
        return data + b"\x00" * (length - len(data))


def _digest_for_diagnostics(ctx: SubstitutionContext) -> str:
    """One-line summary suitable for logs (no PII)."""
    h = hashlib.sha256(ctx.persona_id_text.encode("utf-8")).hexdigest()[:8]
    return (
        f"persona_hash={h} "
        f"session_uuid_set={bool(ctx.session_uuid_bytes)} "
        f"persona_uuid_set={bool(ctx.persona_uuid_bytes)} "
        f"warnings={len(ctx.warnings)}"
    )
