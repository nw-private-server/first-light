# Proposed patch — V3 RegistrationResponse correlation echo

> **Status: Proposed only.** This patch is *not* applied. The
> maintainer should review the rationale and apply at their
> discretion when at a real keyboard with the live client. The
> change is small (~10 lines), safe to revert, and tests a specific
> hypothesis about the V3 retry blocker.
>
> **Hypothesis:** the response's `[8B mystery]` field at body offset
> `0x07..0x0e` is a correlation echo derived from the request, and
> the client retries V3 because our currently-hardcoded captured
> bytes don't match a new session's correlation.
>
> **Time to test:** one live run.

## Background

`server/javelin/v3_response.py` has an 8-byte `mystery8` field
defaulted to the bytes Mixed Nuts captured from a real successful
login: `0b 88 8d 68 70 6c 41 5b`. Those bytes are baked into the
default response template; every V3 response the server sends to
*any* client uses those same bytes.

Per a 2026-05-07 Mixed Nuts spec exchange (see
`docs/post-v3-sequence.md` § "Application-layer C↔S framing"), each
C→S record carries a 16-byte `correlation_uuid` that the project's
parser doesn't currently extract. The hypothesis: the response's
8-byte mystery field is the first 8 bytes (or a derived hash) of
that correlation_uuid, echoed back so the client can match the
response to its request.

If true, every V3 response we send to a new client uses Mixed Nuts's
*old* session correlation, the client doesn't see its own
correlation echoed, and it retries V3 ~every 500ms until the carrier
times out at ~30s — which is exactly the symptom in
`docs/next-session.md`.

The project's V3 request body decode (`analysis/v3_request/BODY_DECODE.md`)
shows an 8-byte "u64 / handle" at body offset `0x06..0x0d`:

```
000  21 03 c5 00 01 00                     prelude (unknown 6B)
006  80 3c 89 54 c1 00 00 03               u64 / handle  (8B)  <-- candidate
00e  bd 0c 00 09 02 00                     unknown sub-header
```

Those 8 bytes are the simplest correlation candidate — first 8
bytes of the V3 request body's prelude after the unknown 6-byte
header.

## What to change

Two small changes in `server/rep_responder.py:_handle_v3_data_record_inner`,
preserving the existing `--ack-form mn|alt` pattern by adding a new
`--mystery-source` CLI selector. The existing default keeps the
captured bytes (no behavior change unless the flag is set).

### Diff

```diff
--- a/server/rep_responder.py
+++ b/server/rep_responder.py
@@ -<line near _handle_v3_data_record_inner>
         req: V3RegistrationRequest | None = None
         try:
             req = parse_v3_request(m.payload)
             sess_uuid_no_dashes = req.session_uuid.replace("-", "")
             if len(sess_uuid_no_dashes) == 32:
                 token = sess_uuid_no_dashes.encode("ascii")
         except Exception as e:
             self.log.debug(f"v3 session_uuid strict-parse failed: {e!r}")
             ...
             req = self._lenient_v3_extract(m.payload)
             ...

-        resp = V3RegistrationResponse(session_token=token)
+        # Optional: echo the request's correlation candidate bytes
+        # (body[6..14] = the "u64/handle" 8B in BODY_DECODE.md) back
+        # in the response's mystery8 field. Hypothesis: client uses
+        # this for request-response correlation; default-baked bytes
+        # are from a different session and cause V3 retries.
+        # See analysis/proposed_patches/correlation_echo_v3_response.md
+        if self.mystery_source == "echo-prelude" and len(m.payload) >= 14:
+            mystery8 = bytes(m.payload[6:14])
+            self.log.info(f"   V3 response mystery8 = echo-prelude {mystery8.hex()}")
+            resp = V3RegistrationResponse(session_token=token, mystery8=mystery8)
+        else:
+            # default: use Mixed Nuts' captured bytes
+            resp = V3RegistrationResponse(session_token=token)
         resp_body = encode(resp)
```

And in the `main()` argparse setup (look for the existing
`--ack-form` definition, add a sibling):

```diff
@@ -<line near argparse setup in main()>
     ap.add_argument("--ack-form", choices=["mn", "alt"], default="mn", ...)
+    ap.add_argument(
+        "--mystery-source",
+        choices=["captured", "echo-prelude"],
+        default="captured",
+        help="V3 response mystery8 field: 'captured' (Mixed Nuts' bytes, "
+             "current default) or 'echo-prelude' (echo request body[6:14]). "
+             "See analysis/proposed_patches/correlation_echo_v3_response.md",
+    )
```

And thread the flag through to `PeerSession`:

```diff
@@ -<PeerSession.__init__>
-    def __init__(self, ctx, peer, sock, ..., ack_form: str = "mn"):
+    def __init__(self, ctx, peer, sock, ..., ack_form: str = "mn",
+                 mystery_source: str = "captured"):
         ...
         self.ack_form = ack_form
+        self.mystery_source = mystery_source
```

(Adjust to whatever the actual `__init__` signature looks like;
this is the shape of the change, not literal copy-paste.)

## How to test

### Pre-condition

Live test environment ready: hosts file redirected, Frida
trust-bypass running, mock server reachable on UDP port 24083.

### Run with default (control)

```bash
python -m server.rep_responder --port 24083
# launch client, observe: V3 retries every 500ms, session dies ~30s
# (current symptom — confirms baseline)
```

### Run with experimental flag

```bash
python -m server.rep_responder --port 24083 --mystery-source echo-prelude
# launch client, observe:
#   - server log: "V3 response mystery8 = echo-prelude 80 3c 89 54 c1 00 00 03"
#     (or whatever the actual u64/handle bytes are for this session)
#   - client behavior:
#     SUCCESS  -> V3 retry stops, state advances past 10
#     FAILURE  -> V3 retries continue (hypothesis is wrong)
```

### Success signal

Most likely positive signals (any one is sufficient):

- The "V3 RegistrationRequest" log on the server stops repeating
  after the first one (currently it prints once per ~500ms).
- The client reaches the post-V3 replay phase (server log shows
  "replay queue armed: N R-msgs" firing).
- A different state-machine log line appears in any Frida hook
  output — e.g. the `"GameConnectionWrapper: actor game connection
  succeeds"` log line that fires on state 10→11 transition (the
  string is at `0x1484ff048` per `analysis/state_machine_summary.md`,
  reached when wrapper substate flips to 2).

### Failure signal

If V3 retries continue uninterrupted, the correlation-echo
hypothesis is wrong. Other candidates to consider next:

- Mystery8 might be derived from request bytes via a hash, not a
  raw byte slice. Try CRC32 over the prelude, or first 8 bytes of
  the auth blob, or some other transformation.
- The 16-byte correlation might be at a different offset — try
  body[0x14..0x1c] (the "CRC32-shaped" 8 bytes) instead.
- The retry might be from a different field entirely. Falling back
  to Frida hook on `FUN_146454c00` (per `state_machine_summary.md`
  § 8) is the next-clearest diagnostic.

## How to revert

```bash
git checkout -- server/rep_responder.py
# or just don't pass --mystery-source on the next run; default is
# unchanged from current behavior.
```

The change is gated on a CLI flag with default = current behavior,
so reverting is just running without the flag.

## Why this is worth trying first

- **Cost:** ~10 lines, single A/B test run, default unchanged.
- **Specificity:** narrows V3 retry root cause to one of two
  things in one observation.
- **Falsifiable:** clear success/failure signal in server logs.
- **Doesn't conflict with later work:** if it succeeds, the project
  proceeds to the post-V3 replay extension. If it fails, the next
  experiment (Frida hook) is unaffected.

## Adjacent open questions this doesn't address

These remain open regardless of patch outcome:

- Whether the captured replay's seq 0x14 area actually contains
  the SelfIdent message (per worklog wake 26's interpretations
  A vs B).
- The CRC32 over (correlation + msg) the project doesn't validate
  on incoming requests.
- The wider 22-phase sequence past seq 0x24 still needs new
  captures.

But state-10 advancement is gated behind V3 acceptance, so if this
patch succeeds, the project gets to test those questions for the
first time.
