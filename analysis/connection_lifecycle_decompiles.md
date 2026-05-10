# Connection lifecycle decompiles — overview

Companion to `state_machine_summary.md`. Covers the decomp files that
implement connection success / fail / V3-build / loading paths but
weren't part of the state-machine writeup. Surfaces enough context
that the dashboard's Decompiles tab cross-links pick these up via
the wake-129 annotation pass.

## Connection-success path

### `javelin_game_on_connection_succeed` — `FUN_14103b570`

The success-side handler called when a `JavelinGame` connection
completes its handshake. Body sketch:

```c
FUN_146453350(*(undefined8 *)(param_1 + 0x200));   // notify session
if (param_2 == 0) {
    FUN_14143e010("JavelinGame::OnConnectionSucceed");  // log
}
FUN_14646da00(param_1 + -0x20, 1);                  // arm a flag
…
```

Logger string `JavelinGame::OnConnectionSucceed` is the anchor for
xref hunting. The handler arms a flag at `param_1 - 0x20` which
gates downstream send paths. This is the function that fires
once the V3 registration is accepted; the state-machine writes at
`+0xa0` (see `state_advance_predicate.txt`) happen later in the
post-V3 sequence.

### `javelin_game_on_connection_fail`

Sibling function for the failure path. Mirrors `_succeed` but
routes into the destroy chain documented in
`state_machine_summary.md`. Useful as a comparison baseline when
reading the success path.

### `connection_success_caller`

The outer dispatcher that decides whether to call `_succeed` or
`_fail`. Already cross-linked from `state_machine_summary.md`.

## V3 RegistrationRequest assembly

### `v3_builder` — `FUN_146b66820`

Constructs the V3 RegistrationRequestV3Msg in-memory before the
strict serializer (`server/javelin/v3_request.py::serialize_v3_request`)
emits the wire bytes. The handler's parameter layout matches the
strict format's field schedule from
`docs/v3_request/BODY_DECODE.md`:

- `param_2` carries `build_version`-shaped u32 + length
- `param_3` is the AzCore-style allocator-ref'd string (see
  `&PTR_LAB_147f479a8` vftable + `"AZStd::allocator_ref"` literal)
- `param_4..param_7` carry the auth-blob fragments, in order

Notable internal calls:

- `FUN_1402b9910` is the AZStd::string copy/append helper invoked
  for each length-prefixed string field — repeats 10+ times in
  this function, mirroring the 10+ length-prefixed slots in the
  strict body.
- `FUN_146403f10` handles the `client_signature` "sig:..." blob.
- `FUN_1417ccf10` handles the platform-name-blob field
  (`"steam|14"` style).

The wire format produced by this function (when serialized
downstream) is exactly what `parse_v3_request` in
`server/javelin/v3_request.py` reads back. The codec library's
`serialize_v3_request` is the Python equivalent.

### `v2_builder`

The legacy V2 RegistrationRequest builder, retained in the
binary as a fallback path. Same overall structure as `v3_builder`
but with a smaller field set (no platform_name_blob, no
sdk_version_tail, etc.). Useful when reading the V3 builder
diff-style.

### `clientconnectionmsg_sender` and `clientconnectionmsg_typeinfo`

The `ClientConnectionMsg` family that delivers the registration
request envelope to the network layer. The `_sender` is the
emit-side wrapper; the `_typeinfo` is the AzCore RTTI registration
for the message type.

## Loading / CMS-fetch path

### `crash_site` — `FUN_1430079a0`

Despite the file name, this is the **CMS HTTP request handler**
(`Loading CMS HTTP Request URL: %s` is the anchor log line). Up
to 5 retry attempts with 50 ms backoff between them; handles 200
and 304 (`0x130`) responses; uses `If-None-Match` for caching.
Was named "crash_site" early in the RE work because an unhandled
HTTP failure here was the proximate cause of an early crash — the
function itself is not the crash, just where the crash chain
became visible.

If the CMS fetch fails, downstream caller propagates a `0xffffffff`
return code which the connection-success path treats as a hard
fail. Useful when triaging "why did the client disconnect right
after auth?" — check for CMS log lines first.

### `loadcontext_no_selfid`

The post-CMS load-context initializer that runs in the no-selfid
branch (i.e., when the client doesn't have a cached
SelfIdentification message). Cross-linked from
`state_machine_summary.md`.

## Why this writeup exists

Wake 129 surfaced cross-references between decomp files and analysis
docs on the dashboard's Decompiles tab. 23 of 39 decomps had no
analysis doc referencing them. This writeup mentions 7 of those
(all the connection-lifecycle and V3-builder family) so the wake-129
cross-link pass picks them up in the next site rebuild. That
gets the dashboard's "📄 related" badge density up without writing
any new code or codec.

Future: similar overview doc for the wrapper-setter family
(wrapper_setter_fa30, fa80, gw160_setter, branchA_sender,
state12_gate_setter_caller, state13_writer_a/b/c, etc.) would
push the cross-link density past 90%.
