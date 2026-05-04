# GridMate-Carrier Compression Algorithm

**Algorithm: LZ4 raw block (no frame header, no size prefix).**

## Evidence

### 1. Visual inspection — token 0x52 is a textbook LZ4 token

LZ4 block format begins with a 1-byte token: `(literals_len << 4) | (match_len - 4)`.

`0x52` decomposes as: **5 literal bytes**, then a **6-byte match** (4 + 2).

Mapping the compressed body byte-by-byte against the expected output:

```
compressed: 52 [21 00 05 03 00] [01 00] b0 [05 02 18 00 06 40 00 07 00 02 06]
            ^token  ^5 literals  ^offset  ^match-len-ext  ^remaining literals
expected:      21 00 05 03 00  00 00 00 00 00 00  05 02 18 00 06 40 00 07 00 02 06
                                ^^^^^^^^^^^^^^^^^^
                                6 zero bytes copied from match
```

The "01 00" is the little-endian back-reference offset (= 1, pointing one byte
back to the just-emitted `0x00`). The next byte `0xb0` is the second token
covering the remaining 11 literal bytes (token hi-nibble = 0xB = 11 literals,
0xF=240 would trigger length-extension but 0xB is final).

### 2. Library round-trip confirms exact match

```python
import lz4.block
compressed = bytes.fromhex('5221000503000100b00502180006400007000206')
out = lz4.block.decompress(compressed, uncompressed_size=22)
# out.hex() == '21000503000000000000000502180006400007000206'  -> EXACT MATCH
```

Re-compressing the expected output with `lz4.block.compress(expected, mode='default', store_size=False)`
yields the **byte-identical** 20-byte stream `5221000503000100b00502180006400007000206`. All three
modes (default / fast / high_compression) produce the same result for this small payload.

Other algorithms tried — all fail:
- `lz4.frame.decompress` — `ERROR_frameType_unknown` (no magic 0x184D2204)
- `zlib.decompress` / raw deflate — header check / distance errors
- `snappy.decompress` — UncompressError
- `zstandard.decompress` — frame header error

### 3. Source confirmation

`docs/gridmate-reference.md:950-952` already documents:
> Stock ships a MultiplayerCompressor (LZ4-based usually); NW may have added its own dictionary.

Our captured packet contains **no preset dictionary** (raw block decompresses
cleanly with default tables), so NW kept the stock LZ4 implementation for at
least the small handshake-era payloads.

## Decoder snippet

```python
import lz4.block

def decompress_carrier_body(body: bytes, max_uncompressed: int = 1500) -> bytes:
    """Decompress a Carrier datagram body when envelope flag bit-0 is set (0x81).
    The body is a raw LZ4 block — no LZ4 frame header, no length prefix."""
    return lz4.block.decompress(body, uncompressed_size=max_uncompressed)
```

`uncompressed_size` is required by python-lz4 because the raw block doesn't
self-describe its output length. A safe upper bound is the driver MTU
(~1400 bytes for UDP — see `docs/gridmate-reference.md:91-94`). Pass a slightly
larger value (e.g. 2048) and trim, or scan for the implicit end via record
parsing.

## Can the server send uncompressed?

**Yes — almost certainly.** Two reasons:

1. The envelope already advertises the choice per-datagram (bit-0 of the type
   byte: `0x80` = plaintext, `0x81` = compressed). The receiver dispatches on
   that bit before attempting decompression — same `Carrier.cpp:2080-2090` path
   our reference quotes for the compression hint byte. If `0x80`-only worked
   for the sender at all, the receiver must accept it.
2. The captured client→server traffic uses `0x80` exclusively (149 datagrams,
   per `project_javelin_envelope.md`); the server only switches on `0x81` for
   payloads where compression is worth it. Mixed flag values within a single
   session is the design intent.

Recommendation: have `rep_responder.py` keep emitting `0x80` envelopes. Only
add LZ4 compression once we hit a payload where the size matters (e.g. replica
state snapshots > ~200 bytes). For handshake/ACK/sysmsg traffic the overhead
isn't worth it and the client will accept plaintext.
