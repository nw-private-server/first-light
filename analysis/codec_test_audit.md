# Codec test audit — wake 125

## Method

Walked `server/javelin/test_codecs.py` (320 test functions) and
bucketed each by the codec module its name references, then
categorized within each bucket as:

- **`round_trip`** — encode→decode or decode→encode byte-identity
- **`captured_replay`** — match against the bundled replay
- **`structural_rejection`** — wrong size, wrong header, broken
  invariants
- **`encode_decode`** — encode-only or decode-only (asymmetric)
- **`other`** — uncategorized

Heuristic-based; the `other` bucket has 231 tests that don't
match the simple keyword categorization (many are property tests
or fixture builders that test the codec implicitly). Future
audits could refine the matchers.

## Per-codec coverage

| Module | rt | cap | rej | enc | other |
|---|---:|---:|---:|---:|---:|
| chunked_stream_08 | 3 | 0 | 3 | 0 | 2 |
| dispatch | 2 | 3 | 2 | 3 | 2 |
| empty_marker_651 | 1 | 1 | 2 | 0 | 0 |
| frame | 1 | 1 | 5 | 0 | 0 |
| handshake_blob_76 | 0 | 0 | 0 | 0 | 2 |
| init_message_18a6 | 0 | 0 | 0 | 0 | 3 |
| keybinding_config_12f6 | 2 | 0 | 0 | 0 | 1 |
| opaque_blob_1033 | 1 | 1 | 3 | 0 | 0 |
| replay_store | 0 | 0 | 1 | 0 | 8 |
| result_token_1097 | 0 | 0 | 0 | 0 | 1 |
| result_token_136a | 0 | 0 | 0 | 0 | 1 |
| self_ident | 3 | 0 | 8 | 2 | 12 |
| session_clock_beacon | 1 | 0 | 0 | 0 | 0 |
| session_identity_beacon | 1 | 0 | 0 | 0 | 0 |
| session_message_a4 | 1 | 0 | 0 | 0 | 0 |
| subkey_beacon | 0 | 0 | 2 | 0 | 1 |
| v3_request | 1 | 0 | 2 | 0 | 0 |

## Gaps: codecs without structural-rejection tests

8 codec modules currently have **zero** tests categorized as
structural-rejection by the heuristic:

| Module | Tests | Gap severity |
|---|---|---|
| `handshake_blob_76` | 2 (other) | `decode()` validates size + header; tests don't exercise rejection paths |
| `init_message_18a6` | 3 (other) | Same — `decode()` has size + header checks not under test |
| `keybinding_config_12f6` | 3 (rt + other) | Round-trip tests exist; rejection paths uncovered |
| `result_token_1097` | 1 (other) | One test, possibly an integration/factory |
| `result_token_136a` | 1 (other) | Same |
| `session_clock_beacon` | 1 (rt) | Round-trip only; size + type-header rejection paths uncovered |
| `session_identity_beacon` | 1 (rt) | Round-trip only; same |
| `session_message_a4` | 1 (rt) | Round-trip only; same |

The three `session_*` modules are the lowest-hanging fruit: each
has a `decode()` that validates size + type header, but no test
actually exercises the failure paths. A 1-2 line `pytest.raises`
test per module raises code-review confidence with minimal
effort.

The two `result_token_*` and `keybinding_config_12f6` are
slightly heavier — their decoders have more invariants to break.

`handshake_blob_76` and `init_message_18a6` are more complex
(family + counter-pair logic) and warrant a dedicated wake to
ensure rejection coverage tracks the structural invariants.

## Wake-125 fix-up

This wake adds three minimal structural-rejection tests for the
session_clock_beacon, session_identity_beacon, and
session_message_a4 modules — the lowest-effort gaps. Each test
exercises the size-mismatch and wrong-header paths for one
representative codec per module.

## Recommended follow-ups (any contributor)

1. **`result_token_1097` + `result_token_136a` rejection tests**
   — small (~10 LOC each).
2. **`keybinding_config_12f6` rejection tests** — its docstring
   mentions a 26-byte opaque state-region; verifying the size
   gate adds one test.
3. **`handshake_blob_76` rejection tests** — covers the shared
   76-byte family for both `0x40a` and `0x1be`.
4. **`init_message_18a6` rejection tests** — counter-coupled
   with `0x1a59`; verify the counter validation path.

After all 8 are filled in, the `Codecs without structural-
rejection tests` count drops to **0** and the audit serves as
the regression bar going forward.

## Heuristic limitations

- 231 tests sit in the `other` bucket (uncategorized).
  The matcher only catches `round_trip`, `captured_replay`,
  `reject*`/`raises`/`wrong*`/`invalid*`/`too_short`/`validates`,
  and `encode`/`decode` substrings. Tests that use unusual
  naming (e.g. `test_session_message_short_buffer`) get bucketed
  as `other` and may already cover rejection paths.
- A more thorough audit would parse the test bodies to detect
  `pytest.raises` calls — that's the real signal for rejection
  coverage. Documenting this as a future audit refinement.
