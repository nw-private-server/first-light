# Codec library — overview

A guide to `server/javelin/` for contributors landing on this repo
for the first time. As of wake 109 the library covers every
captured wire-type message in our DTLS replay; every captured
body decodes successfully and round-trips byte-for-byte through
the unified dispatcher.

## What's in here

The library has three layers, sketched below from low-level wire
plumbing to high-level routing:

```
                ┌─────────────────────────────────────────┐
                │   server.javelin.dispatch               │  ← wake 104+
                │   decode_replay_message()               │
                │   encode_replay_message()               │
                └─────────────────┬───────────────────────┘
                                  │ routes by type-id
              ┌───────────────────┼─────────────────────┐
              │                   │                     │
    ┌─────────▼────────┐  ┌──────▼─────────┐  ┌────────▼───────┐
    │ Per-type codecs  │  │ Family codecs  │  │ Supporting     │
    │  (28 modules)    │  │  (1 module,    │  │  modules       │
    │                  │  │   13 type-ids) │  │  (3 modules)   │
    └──────────────────┘  └────────────────┘  └────────────────┘
                                  │
                ┌─────────────────▼───────────────────┐
                │  Low-level wire plumbing            │
                │  bitstream.py, frame.py, wire.py    │
                └─────────────────────────────────────┘
```

## Layer 1 — wire plumbing

| Module | What it does |
|---|---|
| `bitstream.py` | Bit-level reader/writer for VLQ-encoded fields. Used by `frame.py` and several per-type codecs. |
| `frame.py` | Datagram, record, and system-message framing. Mirrors the binary's `Carrier::ParseMessages` / `Carrier::WriteMessages`. |
| `wire.py` | C→S CRC32 framing helpers. `compute_cs_crc32`, `serialize_cs_envelope`, `parse_cs_envelope`, `fixup_cs_crc32`, `verify_cs_crc32`. |

These three modules are foundational — every codec above sits on top of them.

## Layer 2 — per-type codecs

Each captured wire-type ID has a codec module. They follow a
common shape:

```python
TYPE_HEADER = bytes((0x00, 0x01, ...))   # 4-byte typed envelope header

@dataclass
class FooNNN:
    field_a: int
    field_b: bytes
    ...

def encode(msg: FooNNN) -> bytes: ...
def decode(buf: bytes) -> FooNNN: ...
```

Naming convention: `<purpose>_<typeid_hex>.py`. The hex suffix
makes a module instantly identifiable from a wire type-id.

The 22 per-type codec modules in alphabetical order:

| Module | Wire type | Direction | Coverage depth |
|---|---|---|---|
| `action_history_635.py` | `0x635` | W | structural |
| `asset_blob_16a0.py` | `0x16a0` | R | small=structural, large=opaque |
| `asset_count_table_ca4.py` | `0xca4` | R | structural |
| `chunked_stream_08.py` | `0x08` | R | framing-only (two forms) |
| `empty_marker_651.py` | `0x651` | R | structural (zero payload) |
| `frame_config_1096.py` | `0x1096` | R | structural |
| `handshake_blob_76.py` | `0x40a` / `0x1be` | both | structural (shared family) |
| `heartbeat_15d.py` | `0x15d` | R+W | structural (ping/ack pair) |
| `identity_blob_8e6.py` | `0x8e6` | R | structural |
| `identity_fingerprint_5b2.py` | `0x5b2` | W | structural |
| `init_message_18a6.py` | `0x18a6` | W | structural |
| `keybinding_config_12f6.py` | `0x12f6` | W | structural |
| `level_descriptor_663.py` | `0x663` | R | structural |
| `level_info_changed.py` | (AzCore-style) | R | structural |
| `opaque_blob_1033.py` | `0x1033` | R | framing-only (presumed encrypted) |
| `permission_bitmap_a95.py` | `0xa95` | W | structural |
| `receipt_handshake_9fc.py` | `0x9fc` | W | structural |
| `result_token_1097.py` | `0x1097` | R | structural |
| `result_token_136a.py` | `0x136a` | R | structural |
| `self_ident.py` | (AzCore-style) | W | structural |
| `session_clock_beacon.py` | `0x14f` | R | structural |
| `session_identity_beacon.py` | `0x1b88` | R | structural |
| `session_message_a4.py` | `0xa4` | R | structural |
| `session_subkey_1a59.py` | `0x1a59` | W | structural |
| `v3_request.py` | `0x13` | W | strict + retry-tagged + lenient (3 forms) |
| `v3_response.py` | `0x03` | R | encode-only (server-emit) |
| `vivox_config_1067.py` | `0x1067` | R | structural |
| `world_data_blob_65c.py` | `0x65c` | R | structural |

**Coverage depth glossary**:
- **structural** — every byte mapped to a typed field. Round-trip
  is byte-identical.
- **framing-only** — type header + identity prefix validated; the
  payload tail is preserved as opaque `bytes`. Round-trip is byte-
  identical, but the codec doesn't subdivide the tail's internal
  structure.
- **encode-only** — codec emits but doesn't parse (because the
  message is server-emitted in our role).

## Layer 3 — family + generic codecs

| Module | What it does |
|---|---|
| `subkey_beacon.py` | Generic codec for the 13-type-id subkey-beacon family (`0x66b, 0x9d3, 0xf7f, 0x101a, 0x101d, 0x102e, 0x102f, 0x1098, 0x10b0, 0x143d, 0x187c, 0x187f, 0x192c`). All share the same wire layout; the type-id is carried inside the dataclass. |

## Layer 4 — dispatcher (wake 104-105, 109)

| Module | What it does |
|---|---|
| `dispatch.py` | Central type-id router. `decode_replay_message(type_id, direction, body)` returns the right codec's dataclass; `encode_replay_message(type_id, msg)` returns wire bytes. Direction-aware for `0x15d` (heartbeat); two-form-aware for `0x08`, `0x16a0`; multi-form-aware for `0x13` (strict / retry / lenient chain). |

This is the layer most callers should use. A typical call:

```python
from server.javelin import dispatch

# Inbound: bytes from the wire
msg = dispatch.decode_replay_message(type_id, direction, body)

# Outbound: dataclass back to wire
wire = dispatch.encode_replay_message(type_id, msg)
```

The 0x03 V3 response is intentionally absent from the decode side
(we never receive it, only emit it) but is on the encode side.

## Layer 5 — supporting modules

| Module | What it does |
|---|---|
| `replay_store.py` | Parses the captured DTLS replay (`info/nw-login-safe-*/messages-redacted.txt`) into a list of `Message(seq, type_id, direction, body, has_redaction)`. The reference data source for tests. |
| `replay_substitution.py` | Substitutes live-session identity into captured replay bodies so the post-V3 captured stream can be replayed safely against a real connecting client. |
| `session_state.py` | Per-peer session-state scaffolding. Not yet plumbed into the runtime responder. |

## Hand-debugging: `tools/decode_message.py`

A small CLI that surfaces the dispatcher for human inspection.
Useful when you have a captured body and want to see what the
codec library makes of it without writing throwaway Python.

```sh
# List every wire-type the dispatcher knows about (with capture counts)
.venv/bin/python3 tools/decode_message.py --list

# Decode a captured 0x15d (heartbeat ping) from the replay
.venv/bin/python3 tools/decode_message.py --type 0x15d --replay-index 0 --direction R

# Decode a captured message by seq number directly (more natural for replay analysis)
.venv/bin/python3 tools/decode_message.py --type 0x15d --direction R --seq 0x2

# Decode a raw hex body
.venv/bin/python3 tools/decode_message.py --type 0x15d --direction R \
  --hex '00019d050003af9100000001'

# From a file or stdin
.venv/bin/python3 tools/decode_message.py --type 0x65c --direction R --file /tmp/body.bin
cat body.bin | .venv/bin/python3 tools/decode_message.py --type 0x18a6 --direction W --stdin

# Pipeable JSON output (comments go to stderr so stdout stays clean)
.venv/bin/python3 tools/decode_message.py --type 0x15d --replay-index 0 --json | jq .counter
```

Output is the codec dataclass formatted with `pprint`. Returns a
non-zero exit if the type-id has no registered decoder.

## Tests

`server/javelin/test_codecs.py` is the single test file (~4000+ lines as of wake 145). Conventions:

- Each codec ships round-trip + structural-rejection tests
  (both audited to 0 gaps — see
  [codec_test_audit.md](codec_test_audit.md) and
  [codec_encoder_audit.md](codec_encoder_audit.md)).
- Captured-replay tests use the actual on-disk replay to assert
  byte-identical decode→encode round-trip.
- The dispatcher's full-replay round-trip test (`test_dispatch_encode_decode_round_trip_full_replay`) is the canary: any new codec failure surfaces as a single failing test rather than silent drift.

```sh
.venv/bin/pytest server/javelin/test_codecs.py
# 346 passing as of wake 145 (+1 skipped)
```

## CLI: `tools/decode_message.py`

```sh
# Enumerate every wire-type the dispatcher knows about
tools/decode_message.py --list

# Decode a captured message by replay-index OR by seq (more natural for replay analysis)
tools/decode_message.py --type 0x15d --direction R --replay-index 0
tools/decode_message.py --type 0x15d --direction R --seq 0x2

# Decode raw hex / a file / stdin
tools/decode_message.py --type 0x15d --direction R --hex '00019d050003af9100000001'
tools/decode_message.py --type 0x65c --direction R --file /tmp/body.bin
cat body.bin | tools/decode_message.py --type 0x18a6 --direction W --stdin

# Pipeable JSON (comments go to stderr)
tools/decode_message.py --type 0x15d --replay-index 0 --json | jq .counter
```

## Dispatcher API

`server.javelin.dispatch` is the canonical decode/encode entry point:

```python
from server.javelin import dispatch

# Inbound: bytes from the wire → typed dataclass (or None if 0x03 / unmapped)
msg = dispatch.decode_replay_message(type_id, direction, body)

# Outbound: typed dataclass → bytes (raises KeyError if unmapped)
wire = dispatch.encode_replay_message(type_id, msg)

# Inventory
dispatch.supported_type_ids()   # frozenset of decoder-side type-ids
dispatch.encodable_type_ids()   # frozenset of encoder-side type-ids
```

The dispatcher knows every captured wire-type plus `0x5d1`
(the SelfIdentification trigger for the state-10→11 unblock —
see [state_10_unblock_synthesis.md](state_10_unblock_synthesis.md)).

## Adding a new codec

When a new captured wire-type appears:

1. **Hex-dump and characterize** the body. Look for floats, durations, hashes, repeated fields, zero-pads. The wakes 100-103 worklog entries show this approach in detail.
2. **Pick coverage depth**:
   - Single capture, no observable structure → framing-only (see `opaque_blob_1033.py` as template).
   - Single capture, observable structure → structural (see `frame_config_1096.py`).
   - Multiple captures with shared anchors → use cross-comparison to confirm invariants (see `chunked_stream_08.py`).
3. **Write the codec** following the per-type module shape: `TYPE_HEADER`, dataclass, `encode()`, `decode()`. Validate structural invariants in `decode()` so bad bytes fail loudly.
4. **Add tests** in `test_codecs.py`:
   - **Decode side**: round-trip, captured-replay match, structural-rejection (wrong size, wrong header, broken invariants), constructor width validation.
   - **Encode side**: populated round-trip (fresh dataclass → encode → decode → assert equal). The wake-135/136 audit caught the older codecs that lacked this; new codecs should ship it from day one.
5. **Wire into dispatcher**: add an entry to `DECODERS` and `ENCODERS` in `dispatch.py`. Update `tools/build_site.py`'s `codec_for_type` map so the dashboard shows it.
6. **Run** `.venv/bin/pytest server/javelin/test_codecs.py`. Then run `.venv/bin/python3 tools/build_site.py` so the live badges + dashboard pick up the new test count.

## Audits (both at 0 gaps as of wake 136)

- [`codec_test_audit.md`](codec_test_audit.md) — decoder-side
  structural-rejection coverage. Initial audit (wake 125): 8
  gaps. Closed (wake 126): 0 gaps.
- [`codec_encoder_audit.md`](codec_encoder_audit.md) —
  encoder-side populated round-trip coverage. Initial audit
  (wake 135): 7 gaps. Closed (wake 136): 0 gaps.
- The audit-arc pattern is documented in
  [`cross_link_arc.md`](cross_link_arc.md) — scaffold → wedge
  → close in 2 wakes per arc.
