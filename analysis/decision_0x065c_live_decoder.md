# Decision: 0x065c stays out of the live decoder

**Wake**: 221  &nbsp;|&nbsp; **Type**: design decision, not a finding

## TL;DR

The live decoder stops at **36/40 (90.0%)** after wake 217's 0x12f6
ship. 0x065c (`world_data_blob`) is the last captured wire-type with
a full Python codec but no JS live decoder. This document records
the explicit decision to **NOT ship a JS decoder** for it, and the
criteria that drove the call. The codec remains fully exercised by
the Python test suite; only the dashboard Explore-tab adoption is
declined.

## What 0x065c is

- **Direction**: R (server → client).
- **Phase**: 4 — sent immediately after V3 RegistrationResponse and
  before the 0x40a / 0x1be handshake pair.
- **Size**: **12706 bytes** (single capture, seq 0x6).
- **Records**: 42 variable-size records, most 224 bytes (80 data +
  144 0xFF padding), one ~3744-byte gap record, one trailing
  ~27-byte tail.
- **Codec lives at**: `server/javelin/world_data_blob_65c.py` (~330
  lines, structural; preserves byte-exact round-trip without
  decoding per-record semantics).
- **Redactions**: 32 bytes redacted (two 16-byte spans at offsets 5
  and 12690).

The codec docstring describes it as "structural" — the per-record
state values look meaningful (`58 61 78 14` sub_id, repeating
patterns) but the semantic interpretation isn't recoverable from
one capture.

## The live-decoder boundary

The Explore-tab live decoder optimizes for one specific user
journey: **a contributor pastes a captured hex body, picks the
type, and sees field-aligned output on a single screen** that
helps them understand the wire format. The wake-200 Findings card
calls this "single-screen JS rendering useful to a visitor" — it's
the deciding lens.

Existing decoders meet this bar comfortably:
- **15-byte fields** for 0x15d ping (heartbeat counter + nonce).
- **40 bytes** for 0x18a6 InitMessage (identity-bundle init).
- **42 bytes** for 0x1b88 SessionIdentityBeacon.
- **93+15n** for 0x635 ActionHistory (largest pre-217 ship; ~70 JS
  lines; first 4-5 history records visible in one viewport).
- **299 bytes** for 0x12f6 KeybindingConfig (largest ship; ~85 JS
  lines; 18 keybindings inline).

0x065c is **~14× larger** than 0x12f6. Even a compact
table-of-records rendering — 42 rows × `<offset> | <data-len> |
<ff-padding-len> | <first 8 bytes hex>` — pushes 80+ lines tall.
The visitor's mental model after viewing it is not "I now
understand this wire-format" but "this is a big opaque blob."

## Decision criteria

Three lenses, all pointing the same direction.

### 1. Visitor utility (primary lens)

A visitor inspecting 0x065c in the live decoder learns:
- It's 12706 bytes.
- It has a 4-byte type header at `+0x00`.
- It has 42 records with mostly-FF padding.
- The handshake-family `DEFAULT_SHARED_TRAILER` (36 bytes) matches.

That's interesting but **not actionable** — none of the per-record
content is decodable without a second capture to compare against.
The visitor leaves no better equipped to RE the format.

By contrast, decoding the 4 already-shipped largest types (0x16a0,
0x663, 0x1067, 0x12f6) **does** equip the visitor: they see real
strings (vivox URL, level name), real counters, real flags.

### 2. Maintenance cost

A 0x065c JS decoder would be **120-150 lines** based on the
extrapolation from 0x635 (~70 lines @ 93+ bytes) and 0x12f6 (~85
lines @ 299 bytes). The DECODER object alone would be the largest
in `site/index.html`. Future codec-shape changes would require
synchronized updates across both the Python codec AND the JS
decoder, raising the bar on every refactor.

### 3. Coverage-vs-completeness trade-off

The dashboard live-decoder coverage badge currently reads
**90.0%** (`36/40`). The wake-200 Findings card now lists 4
remaining uncovered types:
- **0x0003** — server-only, no captured-side decode possible
  (structural).
- **0x0008** — meta-codec (chunked_stream framing), not a single
  message (structural).
- **0x0013** — encoder-only path, we don't reply-decode our own
  V3 sends (structural).
- **0x065c** — *this doc's subject*.

Three of the four are **structurally untestable**. Shipping
0x065c would tick coverage to 92.5% but the remaining three would
still floor at 92.5%. The optical jump from 90% → 92.5% is small;
the optical clarity of "we stopped at 90% because the last
candidate failed the visitor-utility bar" is larger.

## Decision

**The live decoder stops at 36/40 (90.0%).** 0x065c stays
Python-only. The wake-200 Findings card text already reflects this
implicitly; this doc makes the rationale explicit for a future
contributor who looks at the uncovered list and wonders why.

## Reversal criteria

Re-open this decision if:
1. **A second 0x065c capture lands** that lets per-record semantics
   be decoded (cross-capture diff). Then a JS decoder would
   actually be useful — the visitor could see structure, not opaque
   bytes.
2. **The dashboard adds a "large-blob" rendering primitive**
   (collapsible per-record drawers, hex-viewer with offset
   navigation, etc.) that changes what "single-screen" means.
3. **Coverage symmetry becomes a stated goal** (e.g. "every
   non-structural type must have a live decoder"). The current
   goal is visitor utility, not coverage percentage.

Until then: 90.0% is the floor by design, not by accident.

## See also

- Wake-200 Findings card on the dashboard ("Remaining 4 uncovered
  wire-types: structural reasons") — surfaces this decision in
  one-paragraph form.
- Wake-192 Findings card ("Live decoder addresses 90%...") —
  narrates the progression that reached this floor.
- `server/javelin/world_data_blob_65c.py` — the Python codec that
  remains fully exercised.
