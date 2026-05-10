# Wire-type 0x08 — structural investigation

## Capture profile

- **Direction**: R (server → client) — all 79 captures
- **Captures**: 79 (the highest count of any captured wire-type)
- **Body sizes**: 78 B → 46 423 B (47 distinct sizes)
- **Largest message in the entire replay** is a 0x08 at seq 0x25
  (46 423 bytes — opens the session, plausibly a world-data dump)

## Two forms

### Standard form — 78/79 captures

11-byte anchor invariant across all 78 bodies:

```
+0x00  4   prefix              `00 01 08 01`
+0x04  1   subtype             varies (54 distinct values; 0x01 most
                                common at 24/78)
+0x05  6   constant            `01 01 01 01 00 00`
+0x0b  …   opaque tail         variable
```

The constant region at +0x05..+0x0a is 100% stable — verified
byte-for-byte across every standard capture.

### UUID-prefixed form — 1/79 captures (seq 0x25)

The session-opening 46 423-byte message does not start with the
standard prefix:

```
+0x00  16  uuid                `03 87 94 2a 66 1f 85 43 1d 45 8b 40
                                  d2 1f 3b 26`
+0x10  …   opaque tail         46 407 bytes
```

The 16-byte UUID is consistent with bundling session identity at
the start of a bulk dump.

## Subtype byte distribution (standard form)

The byte at +0x04 splits the standard captures into apparent
subgroups:

| subtype | count |
|---|---|
| `0x01` | 24 |
| `0x22` | 3 |
| `0x30`, `0x2e`, `0x23`, `0x2c`, `0x35`, `0x32`, `0x16`, `0x07` | 1 each |
| (39 other distinct values, 1 capture each) | 39 |

The 24 captures with `subtype=0x01` likely share a common payload
shape; the others are subtype-singletons in this replay. A second
session capture would let us cluster the 39 singletons by subtype.

## Correlation marker — present, but inline

The 8-byte sequence `03 65 f2 69 14 78 61 58` (ASCII tail "xaX")
appears **inside** the opaque tails of 25 captures, but **not** as
a chunk separator at the wire level:

| Body size range | Captures | Avg markers per body |
|---|---|---|
| 0–200 B | 5 | 1.4 |
| 200–1000 B | 28 | 2.5 |
| 1000–5000 B | 15 | 1.5 |
| 5000–50000 B | 30 | **0.0** |

If the marker were a structural chunk separator, the largest
messages (which most plausibly carry "many chunks") would have
the most markers — but they have zero. The marker is therefore
treated as inline data, presumably a session/sub-system
correlation token similar to the project-wide identity-bundle
markers (wake 78). Codec-side it lives inside `opaque` and gets
no special handling.

## Codec status

`server/javelin/chunked_stream_08.py` exposes both forms:

- `ChunkedStream08Standard(subtype, opaque)` — round-trips the 78
  standard captures byte-for-byte.
- `ChunkedStream08UuidPrefixed(uuid, opaque)` — round-trips the
  outlier byte-for-byte.
- `decode_either(buf)` / `encode_either(msg)` dispatch by sniffing
  the leading 4 bytes.

The codec validates the 11-byte anchor strictly (prefix +
constant region) so that any future capture that doesn't match the
known forms will fail loudly rather than silently.

This brings captured-type codec coverage to **40/40**. All
40 captured wire-types in the replay are now handled by the codec
library (with varying degrees of structural depth — see the
worklog wakes 86-103 for per-type investigations).

## What would unblock subtype-aware decoding

The opaque tail's structure depends on the subtype byte at +0x04.
Three options to crack this further:

1. **More captures**. With multiple captures per subtype, common
   structure within a subtype (similar to wake 101's 0x1096) will
   surface. The current replay has 24 captures of `subtype=0x01`
   but only 1 each for most other subtypes, so subtype clustering
   would already work for `0x01` alone.
2. **Runtime trace** of the function emitting `0x08`. The subtype
   byte likely names a sub-record format (TLV tag + body). A
   Frida trace at the emitter would expose the per-subtype
   schema directly.
3. **Static-RE on the per-subtype handler**. The dispatch table
   that routes `0x08` by subtype byte should be findable in the
   binary; once located, decompiling the `0x01` handler would
   give us the most-common subtype's schema.

Until then, the framing-only codec correctly identifies the
subtype, validates the wire-level anchor, and round-trips all
79 captured bodies.
