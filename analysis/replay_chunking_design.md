# Replay-message chunking (MF_CHUNKS) design

Status: DRAFT for review — no production code yet.
Date: 2026-05-05

## 1. Problem

`server/rep_responder.py::_send_replay_message` currently caps replay
record bodies at 65 535 bytes (the Carrier record's u16 size field). Any
captured message larger than that gets logged-and-dropped instead of
shipped. The blocker for the next live test is seq 0x29: a 99 819-byte
init StateBundle that we can't fit in a single record.

The Carrier protocol already has a built-in answer — the `MF_CHUNKS`
flag (bit `0x04`) splits one logical message across N records sharing
the same channel. The community state-machine dump (`docs/community/
community_state_machine_dump.txt:39`) confirms a real server uses this
for the `WORLD DATA 0x9c` (12 708 B → 12 segments × ~1 115 B each).

## 2. Wire format (already understood)

Per `server/javelin/frame.py:14-22` and the community dump:

```
flag-byte:   ... | MF_CHUNKS(0x04) | ...
size:        u16BE  (record body size, ≤ 65 535)
[channel]:   u8    if MF_DATA_CHANNEL set
numChunks:   u16BE if MF_CHUNKS set (chunks-countdown)
[seq]:       u16BE if MF_SEQUENTIAL_ID NOT set
[relSeq]:    u16BE if MF_SEQUENTIAL_REL_ID NOT set
payload:     <size-N> bytes
```

`numChunks` is a **countdown**, not an index: the first chunk records
the total count, each subsequent chunk records (count − 1), the last
chunk has `numChunks = 1`. The client reassembles based on this.

## 3. Constraints + sizing

- **Per-record cap:** 65 535 bytes (Carrier u16 size).
- **Per-datagram cap:** loopback MTU is much larger than 1 500 (Windows
  reports 65 KB on the loopback adapter), so on `127.0.0.1` we can
  ship one large datagram or one record per datagram. Network-side
  this would need to be ≤1200 to be safe; loopback we have headroom.
- **Captured chunk size from real server:** ~1 115 B/chunk for the
  WORLD DATA case. Reasonable target.
- **Reassembly buffer:** the client allocates a buffer of size
  Σ(chunk_payload_sizes), so chunks just need to be concatenated in
  order; no chunk-size header inside the payload.

## 4. Proposed API

### 4.1 Helper: `_chunk_replay_payload(body: bytes, chunk_size: int)`

Module-level helper in `rep_responder.py` (or new file
`server/javelin/chunking.py` if it grows). Splits a body into a list
of `(num_chunks_remaining, payload_slice)` pairs.

```python
def _chunk_replay_payload(
    body: bytes, chunk_size: int = 1100,
) -> list[tuple[int, bytes]]:
    """Split a body into chunks for MF_CHUNKS transmission.

    Returns [(remaining, slice), ...] where the first tuple's
    `remaining` equals the total chunk count. Each subsequent
    `remaining` decrements; the last is 1.

    Single-chunk fallthrough: if body fits in chunk_size, returns
    [(1, body)] — caller decides whether to bother setting MF_CHUNKS.
    """
    if not body:
        return [(1, b"")]
    n = (len(body) + chunk_size - 1) // chunk_size
    return [
        (n - i, body[i * chunk_size:(i + 1) * chunk_size])
        for i in range(n)
    ]
```

### 4.2 Caller change in `_send_replay_message`

Replace the current "drop if too big" branch with a chunked path. The
VLQ32 size prefix lives on the FIRST chunk only — it describes the
total-message length, not the chunk-payload length, so chunks 2..N
ship just `body_slice` (no per-chunk VLQ32).

Critically the **u16 record-size field on each chunk** is the
chunk-record's own size (flags + sub-header + per-chunk payload),
not the total message size.

```python
CHUNK_PAYLOAD_SIZE = 1100  # match real-server segment size

if len(envelope_body) <= 0xFFFF:
    # Existing single-record path (no MF_CHUNKS)
    record = ...
    self.send_app(self.wrap_envelope(record))
else:
    # Chunked path
    chunks = _chunk_replay_payload(envelope_body, CHUNK_PAYLOAD_SIZE)
    for i, (remaining, payload_slice) in enumerate(chunks):
        flags = 0x21 | 0x04  # MF_RELIABLE | MF_DATA_CHANNEL | MF_CHUNKS
        c_seq, c_rel = self._next_seq(ch, reliable=True)
        record = (
            bytes([flags]) +
            struct.pack(">H", len(payload_slice)) +    # per-chunk size
            bytes([ch & 0xFF]) +
            struct.pack(">H", remaining) +              # MF_CHUNKS field
            struct.pack(">H", c_seq & 0xFFFF) +
            struct.pack(">H", c_rel & 0xFFFF) +
            payload_slice
        )
        self.send_app(self.wrap_envelope(record))
        self.drain_outbound()
```

Each chunk gets its own `seq`/`rel_seq` from `_next_seq`. They MUST be
sequential per channel — that's what lets the receiver know they
belong together.

### 4.3 Pacing question

The community dump notes the CH1 burst at +460 ms is "47 units, paced
3/batch with 300 ms gaps" — so the real server doesn't fire all chunks
back-to-back. We may need to pace chunks too. Proposal:

- v1: ship all chunks back-to-back in one `_send_replay_message` call.
  Trust DTLS/UDP buffering on loopback.
- v2 (if v1 floods): introduce `--chunk-batch` (chunks per `_pump_replay`
  tick) and `--chunk-batch-gap-ms` (extra pause after a chunked message).

Start with v1 — loopback ordering is reliable, and we can iterate from
real failure modes.

## 5. Where the substitution context plugs in

The substitution layer operates on the WHOLE message body, not the
chunked slices. So:

```
ReplayMessage(body=99KB, has_redaction=True)
  -> ctx.apply(msg) -> 99KB substituted bytes
  -> envelope_body = vlq32(99KB) + substituted bytes
  -> _chunk_replay_payload(envelope_body, 1100) -> 91 chunks
  -> ship each chunk as MF_CHUNKS record
```

The substitution count, length-preservation invariant, and warning
accumulation are all unaffected — chunking happens after substitution,
on the already-substituted bytes.

## 6. Test plan

### 6.1 Unit tests

`server/test_chunking.py`:

- `_chunk_replay_payload` boundary cases:
  - empty body → `[(1, b"")]`
  - exact multiple of chunk_size → no short final chunk
  - non-multiple → final chunk shorter
  - body smaller than chunk_size → `[(1, body)]`
  - countdown decrements correctly (last is 1, first is N)

### 6.2 Integration check

A round-trip test that builds an oversized fake `ReplayMessage`,
runs it through `_send_replay_message`, captures the emitted
datagrams, parses each via `frame.parse_datagram`, and asserts the
concatenated payloads reconstruct the original body.

### 6.3 Live test

`--replay-after-v3 --replay-include-redacted --replay-max-seq 0x29`
should now ship the 99 KB seq 0x29 split into ~91 chunks. Look for:
- All 91 chunks logged with decrementing `remaining` countdown
- Client carrier-acks every chunk
- Render-thread crash either averted or shifts to a new offset

## 7. Risks + open questions

| Risk | Mitigation |
|------|------------|
| 1100 B per chunk too large for some captured StateBundles. | Default 1100, expose via `--chunk-size` CLI flag. |
| Client expects chunks within a tight time window; back-to-back send saturates the receive buffer. | Add `--chunk-pacing-ms` CLI; default 0; tune from log. |
| `MF_RELIABLE | MF_CHUNKS | MF_DATA_CHANNEL` is the right flag combo for chunks 2..N. | Mirror first chunk's flags exactly; let MF_SEQUENTIAL_ID/REL_ID inheritance work via the writer's auto-detect. |
| The `out_msg_seq[ch]` counter advances by N per chunked message, possibly wrapping around 0xFFFF. | Existing `& 0xFFFF` masks already handle wrap. |
| `_pump_replay` pops one ReplayMessage per tick → all 91 chunks ship in one tick. If the client struggles, switch to chunk-per-tick. | v2 pacing CLI flag. |

## 8. Things this design intentionally does NOT do

- **Does not introduce a new pump loop**. Chunks of one message all
  ship within a single `_pump_replay` invocation (atomic from the
  caller's POV).
- **Does not handle inbound chunked messages**. We're the server;
  client → server already works because the parser handles MF_CHUNKS.
  This is purely outbound.
- **Does not implement LZ4 compression** (`0x8101` envelope variant).
  Real server compresses ~59 % of datagrams; we stay uncompressed for
  now. Compression is a separate optimization.

## 9. Estimated effort

- ~30 lines of code (`_chunk_replay_payload` + the caller branch)
- ~50 lines of unit tests
- One small CLI flag for chunk-size
- One PR, doc-only follow-up if pacing becomes necessary
