# Handoff — 2026-05-05 → next session

## TL;DR

V3 RegistrationResponseMsg is byte-correct and the deserializer accepts it
(`successFlag=1`). `rep.ready` flips 0→1 within ms of our reply.
Player visually advances past character creation. Then ~20-50s later,
the rep state handler `FUN_146b3c250 + 0x58f` calls
`FUN_145dca650(transport, -1, reason=0)` — destroys all session items,
resets `rep.ready=0`, screen stays black, eventually session terminates.

The client keeps re-sending `RegistrationRequestV3Msg` every ~500ms the
entire time, as if it never received the reply. **That's the wall to
break next.** Echoing the request's `session_uuid` back as the
`session_token` (as the client originally generated) was a correctness
improvement but did NOT change retry behavior — so the validation gate
isn't `session_token == request.session_uuid`.

## What works

- DTLS 1.2 handshake with our self-signed cert (Frida `verifyField` null patch on `FUN_145dce750`)
- Connect ACK in byte-perfect Mixed Nuts shape (flag 0x21, rel_seq=0)
- V3 RegistrationResponseMsg deserializes (Frida confirms `successFlag=1`)
- Receive handler `FUN_1464755e0` fires
- `rep.ready` flips 0→1
- Replay mode streams 33 captured 0x2..0x24 R-direction messages from `info/nw-login-safe-20260502-153840` after V3 acceptance (all delivered, all carrier-acked, but doesn't change client behavior)
- Auth mock + ETag fix (CTD at NewWorld+0x3007ec3 fixed)
- Character creation UI advances visually

## What doesn't

- **Client never stops retrying V3.** Continues at ~500ms cadence even after V3 response is accepted at every observable layer.
- After ~20-50s of retrying, `FUN_146b3c250 + 0x58f` triggers a destroy-all of session items (`reason=0x0`), and the session winds down.
- World stays black post-character-creation while waiting for post-registration data we haven't identified.

## The exact open question

**Why does the V3-retry loop in `REP_state10_dispatcher` (0x146b6e190) BRANCH B not stop after our response is accepted?**

Two paths to investigate:

### Path A — find what gates the retry loop client-side

`REP_state10_dispatcher` is called every rep-wrapper tick. When `gw[0x160]==1` (which it is), it always builds and sends V3 via `FUN_146b66820` with no conditional check on "did we get a response?". So the retry-stop must come from:

1. The wrapper transitioning OUT of state 10 — but Frida shows state stays at 10
2. Some other byte/field on the wrapper or gateway that, when set, skips the dispatcher entirely

Look at `FUN_14646d460` (the wrapper-tick at RVA `0x0646d460`). It calls `FUN_14644a070` (gameconn_state) which is what actually drives state transitions. Decompile that and find:
- Where it advances state past 10 — what condition triggers the transition
- Whether it polls a property on the GameConnection that the receive handler set

`FUN_1464755e0` (the receive handler) does:
```c
lVar1 = *(longlong *)(DAT_14a7ba0e0 + 0x60);
(**(code **)(*(longlong *)(lVar1 + 0x28) + 0x2d0))(lVar1 + 0x28, "Server version", param_2);
plVar3 = *(longlong **)(*(longlong *)(param_1 + 8) + 0x1000);
_Src = (undefined8 *)(**(code **)(*plVar3 + 0x50))(plVar3, local_58);  // extract string
// strlen + memcpy -> local_38
(**(code **)(*(longlong *)(lVar1 + 0x28) + 0x110))(lVar1 + 0x28, local_38);
```

It sets two properties via vtable on `lVar1+0x28` (the GameConnection):
- vtable[0x2d0]: `("Server version", param_2)` — likely just a debug-property setter for telemetry
- vtable[0x110]: `(extracted_string)` — sets some other property based on a string from the response

The string extracted via `vtable[0x50]` of `*(*(param_1+8) + 0x1000)` is what gets stored. **Find what string this is** — it's probably the session_token, but might be the version_string or something else. If we're sending the wrong format, vtable[0x110]'s setter may reject it without complaining. Then a later wrapper-tick poll sees the property is unset and the state never advances.

### Path B — find what flips `[R13+0xfd]` (the destroy trigger byte)

`FUN_146b3c250 + 0x58f` only fires the destroy loop when `[R13+0xfd] != 0`. Find what writes to `R13+0xfd`. Likely a "registration timed out" flag set by a sibling wrapper-tick check — but if we can identify what it checks before setting the flag, that tells us the same thing as Path A.

Concrete experiment: Frida hook on writes to the byte at offset 0xfd of the connection object. Need to first identify what `R13` is (probably `wrapper+0x14e0` based on the `FUN_14646d460` decomp where `lVar1 = *(longlong *)(param_1 + 0x14e0)` is the session being checked).

## Other loose ends

- **NEW message type from client: `flags=0xfc seq=1 rel_seq=0 payload_len=37-38`.** Appearing 19+ times interleaved with V3 retries last run. Our parser misclassifies them as V3 (matches `flags & 0x40`). One decoded payload: `ffff 0000 0406 210024000001000165c50b2b0000001c000100b001 9d0500036ef6af912d74`. The trailing 12 bytes are LITERALLY the body of our PingMsg replay (seq 0x2 type 0x15d). Client is bouncing the replay back somehow. Whether this means "rejected" or "ack-by-echo" or "routed elsewhere" — undecoded. The leading `ffff 0000 0406` looks like an outer chunk header (MF_CHUNKS=0x04 in flag, so chunks-countdown is in payload?) followed by a nested record `21 0024 00 0001 0001 ...`.

- **Replay rel_seq fix** (`1515880`) and **lenient session_uuid echo** (`ade0eff`) are deployed and correct — but neither changed client behavior. Keep them; they're not the bug.

- **22-phase post-registration roadmap** (`docs/community/community_state_machine_dump.txt`) is from a DIFFERENT reverser's protocol path (state-13 / WaitingForPlayerSpawn / `isMasterPlayer=0` patches). The Mixed Nuts path (which we're following) has a different post-V3 sequence. The 177-message capture in `info/nw-login-safe-20260502-153840` is from Mixed Nuts' path — that's our replay source.

- **Mixed Nuts also bundled a `flag=0x20 ch=3` keepalive ACK record alongside the V3 response in the same envelope** (the `20 00 00 06 03 00 03 00 00 40 00 0c 00 02 06` line in his Discord dump, ending in `02 06` = SM_CT_ACKS). We don't bundle this. Maybe needed; probably not.

## Frida hooks currently active

All in `tools/client-hooks/frida_dtls_hook.js`:

- `internal_response_unmarshal` (0x007cd040): logs `[v3-resp-unmarshal] enter ... bytes=...` and `leave errCode=N successFlag=N` for the RegistrationResponseMsg deserializer
- `internal_response_receive` (0x064755e0): logs `[v3-resp-receive] !! HANDLER FIRED` when the GameConnectionWrapper receive handler runs
- `internal_rep_ready_setter` (0x06b6f190): logs `[rep-ready] setter readyBefore=N readyAfter=N`
- `internal_rep_ready_reset` (0x06b6e7c0): logs `[rep-ready] reset readyBefore=N readyAfter=N` + 20-frame backtrace every fire
- `internal_gridmate_destroy` (0x05dca650): logs `[gm-destroy] enter transport=... obj=... reason=0xN` + 20-frame backtrace
- `internal_rep_wrapper_tick`: logs `[rep-wrapper] tick state=N` per tick

## Files to read first in next session

1. `docs/progress.md` — entries dated 2026-05-04 (latest), 2026-05-04 (later), 2026-05-05 cover everything since V3 wall
2. `info/nw-login-safe-20260502-153840/handoff-notes.md` — Mixed Nuts' description of the working login flow and the `interest=91` StateBundle gate
3. `~/.claude/projects/.../memory/MEMORY.md` — running index. `project_v3_response_accepted.md` is the relevant breakthrough note.
4. `analysis/decomp_response_unmarshal.txt` — the FUN_1407cd040 decomp showing the 5 fields the deserializer reads
5. `server/javelin/v3_response.py` — the 88-byte template that's accepted
6. `server/javelin/replay_store.py` + `server/rep_responder.py` `_handle_v3_data_record` / `_start_replay` / `_pump_replay` — the working replay path

## Suggested first action

Decompile `FUN_14644a070` (gameconn_state, RVA `0x0644a070`). That's the function called per wrapper-tick that drives state transitions. Find the path from "state=10 + receive handler fired" to "state=11" — the missing piece is whatever check it does between those.

If `FUN_14644a070` reads a specific property on the GameConnection that the receive handler sets via vtable[0x110], that property's expected format is the next thing to fix. If it reads a flag at a fixed offset, hook writes to that offset to find what should set it.

Either way, the answer collapses to one of:
- "our response data has a wrong field" (e.g., the trailer 4 bytes, the mystery8, or the version string format)
- "we're missing a follow-up server message" (some specific type the wrapper polls for)
- "we need to send a Carrier-level reliable ACK on the V3 request itself" (currently we don't)

The third one is the cheapest to test: try ACKing the V3 RegistrationRequest at the Carrier reliable layer (a `flag=0x18` piggyback ACK record in the same envelope as the V3 response, like Mixed Nuts does in his Connect ACK). It's a 5-line code change and either fixes it or rules it out.

## Run command (current)

```
python -m server.rep_responder --replay-after-v3
```

Add `--verbose` for debug-level. `--replay-max-seq 0x80` to push past 0x24 if/when we want to test extending the replay (will hit redacted bytes; need substitution code first).

## Latest session logs of note

- `capture/responder_20260505_010708.log` — most recent run, 38 V3 retries, lenient session_uuid echo working, 19 chunked `flags=0xfc` messages
- `capture/20260505_010710_frida_capture/session.log` — Frida log for same run, has the destroy backtrace
- `capture/responder_20260505_004921.log` — earlier run, 97 retries, before lenient echo (similar destroy pattern)
