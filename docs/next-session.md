# Handoff — 2026-05-06 → next session

## TL;DR

The V3 retry wall is broken (#5), the replay pipeline is complete
(substitution + DTLS-safe chunking + post-replay heartbeat — #7, #11,
#13, #15), and the connection now holds indefinitely after V3.

Wall now: **REP wrapper stays at state 10 forever.** Game shows a
black screen post-character-creation; no SM_DISCONNECT; client just
carrier-acks heartbeats. The wrapper-tick (`FUN_14644a070`) reads
some property of the GameConnection per-tick to decide when to
advance from state 10 to 11; the property it reads is unknown.

Latest run (`capture/responder_20260505_215611.log` +
`capture/20260505_215613_piggyback_test_2/session.log`):
- Frida hook on `vtable[0x110]` confirmed it's called once on V3
  accept with the **session_token** (the 32-char hex form of the
  client's `session_uuid`, which we echoed back), and again ~63 s
  later with an empty string. Source of the empty-string write is
  unknown.
- So the receive handler's `vtable[0x110]` ("SetVersionString" per
  decomp) actually stores the **session_token**, not a version
  string. Names in the decomp are misleading.

## What works

- DTLS 1.2 handshake with self-signed cert (Frida `verifyField` null
  patch on `FUN_145dce750`)
- Connect-ACK in byte-perfect Mixed Nuts shape (flag 0x21, rel_seq=0)
  + bundled `flag=0x18` inline ACK
- V3 RegistrationResponse deserializes (Frida confirms `successFlag=1`)
  and `rep.ready` flips 0→1
- Carrier-level piggyback ACK (flag 0x20 ch=3 SM_CT_ACKS) bundled
  with the V3 response stops the V3 retry loop entirely (#5)
- Full 0x2..0xb0 replay ships clean: substitution for redacted UUID/
  persona-id spans (#7), DTLS-safe chunking (max single record 14 KB,
  larger bodies split via MF_CHUNKS at 1100 B/chunk — #11, #13)
- Post-replay heartbeat re-sends the captured PingMsg (type 0x15d,
  12 B) every 500 ms; connection holds indefinitely (#15)
- Auth mock + ETag, all 84 pytest tests green on Python 3.11+3.12
- Dashboard TUI at `tools/dashboard.py` for live-test monitoring (#19)

## What doesn't

- Wrapper stays at state 10. Frida `[rep-wrapper] tick` only ever
  shows states 9 and 10. World never spawns. Game UI: black screen.
- 63 seconds after V3 accept, *something* writes an empty string to
  the same property `vtable[0x110]` set on V3 accept. Source unknown
  but reproducible.

## The exact open question

**Why doesn't the wrapper advance from state 10 to state 11?**

We confirmed `gw[0x160]==1` (BRANCH B in the state-10 dispatcher).
We confirmed our V3 response stores the session_token correctly via
`vtable[0x110]`. We confirmed `rep.ready=1` is held. None of those
appear to be the gate.

The state-advance condition is in `FUN_14644a070` (gameconn_state,
RVA `0x0644a070`), called per wrapper-tick by `FUN_14646d460`. We
don't have it decompiled — Ghidra was running for ~3.5 hours before
being killed.

## Three concrete next experiments

### 1. Decompile `FUN_14644a070`

When time permits, restart `ghidra analyze --detach` against the
project at `analysis/ghidra_project/NewWorld` and let it finish
overnight (memory: `feedback_ghidra_cli_setup.md`). Then:

```
ghidra decompile 0x14644a070
```

That decomp will likely answer the state-advance question outright:
which field on the GameConnection (or on a peer object) does the
tick poll, and what value triggers state→11.

### 2. Read the post-V3 vt[0x110] string content (already shipped)

PR #20 added `readAzString()` to the Frida hook. Next live run will
print the actual decoded version-string content — confirming whether
it's exactly `5b566009bef54dbfa7c76a88e41c1d47`-shaped (= the session
token), or a real version string. We already know from the captured
hex blob that it's the session_token; the decoded form will just
make logs more readable.

### 3. Hook more of the post-V3 receive path

`FUN_1464755e0` decompiled has TWO vtable calls (0x2d0 and 0x110).
We hooked both. But the wrapper-tick reads SOMETHING on the
GameConnection each tick, and that something might be a different
property than what these two setters write to.

Practical next move: hook the wrapper-tick `FUN_14644a070` itself
when Ghidra is up — log every memory access in the first ~20 bytes
of the tick (state-machine reads). Or, more lightweight: stalker-
trace the function once on the first tick after V3 accept and see
what offsets it reads.

## Files to read first in next session

1. `docs/progress.md` — entry "2026-05-05 (evening) -- V3 retry
   wall broken via piggyback Carrier ACK" + its follow-up
   subsection covers everything in this session
2. `~/.claude/projects/.../memory/MEMORY.md` — running index. The
   relevant new entries are:
   - `project_v3_retry_wall_broken.md`
   - `project_render_destroy_was_normal_teardown.md`
   - `project_heartbeat_works_state10_stuck.md`
   - `project_typeregistry_decoded.md`
3. `info/typeregistry.json` — 312 named GridMate RPC types with
   wire-IDs (typeIndex). `SpawnActorsMsg=0x23e` is the spawn-
   trigger but is NOT in the captured replay.
4. `info/community_22_phase_in_game_dump.txt` — community team's
   parallel state machine; useful but their state-13 is not the
   same as our state-10.
5. `analysis/replay_substitution_design.md` and
   `analysis/replay_chunking_design.md` — context for the replay
   pipeline.
6. `tools/client-hooks/frida_dtls_hook.js` — all the Frida hooks
   currently active.

## Frida hooks currently active

(in `tools/client-hooks/frida_dtls_hook.js`)

- `internal_response_unmarshal` — V3 RegistrationResponseMsg deserializer
- `internal_response_receive` — receive handler `FUN_1464755e0`
- `internal_rep_ready_setter` / `internal_rep_ready_reset` — rep.ready
  transitions with backtraces
- `internal_gridmate_destroy` — `FUN_145dca650` with reason byte
- `internal_gameconn_state` — `FUN_14644a070` entry/leave
- `internal_gameconn_wrapper_tick` — `FUN_14646d460` with state field
- `gameconn-vt 0x2d0` — dynamic hook on `GameConnection.SetProperty`
- `gameconn-vt 0x110` — dynamic hook on `GameConnection.SetVersionString`
  (decodes the AZStd::string content, not just struct hex)

## Run commands (current)

```
# Three programs in three Admin terminals (per docs/capture-guide.md)
python -m server.auth_mock --port 443
python -m server.rep_responder --replay-after-v3 --replay-include-redacted --replay-max-seq 0xb0 --character-display-name "NWPrivateTester01"
python tools\client-hooks\frida_capture.py --exe "G:\NewWorldArchive\GameClient\Bin64\NewWorld.exe" --name <test_name>

# 4th terminal: live dashboard (no Admin needed)
python tools\dashboard.py
```

`--post-replay-heartbeat-ms 500` is on by default; pass `0` to disable.

## Latest session logs of note

- `capture/responder_20260505_215611.log` + `capture/20260505_215613_piggyback_test_2/session.log`
  — most recent run; Frida vtable hook decoded the session_token store
- `capture/responder_20260505_205044.log` + `capture/20260505_205050_piggyback_test_2/session.log`
  — first run with full 0x2..0xb0 replay; revealed gm-destroy at
  `+0x14b620f` is normal teardown, not a crash
- `capture/responder_20260505_211537.log` + `capture/20260505_211538_piggyback_test_2/session.log`
  — first run with heartbeat working; 76 s of stable connection,
  113 heartbeats, no disconnect

## Session stats (2026-05-05)

PRs merged: 16 (#5 through #20). All on `main`. CI green on
Python 3.11 + 3.12. Repo is `nw-private-server/first-light` on
GitHub.
