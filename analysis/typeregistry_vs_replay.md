# typeregistry.json vs. captured replay — gap analysis

Generated 2026-05-06 from `info/typeregistry.json` (3487 entries, 312 named)
and `info/nw-login-safe-20260502-153840/messages-redacted.txt` (177 records,
138 R / 39 W). The reusable diff lives in
[`tools/typeregistry_diff.py`](../tools/typeregistry_diff.py).

## Headline numbers

| Bucket | Count |
|---|---|
| Records in capture | 177 (R=138, W=39) |
| Distinct wire types observed | 40 |
| ↳ named in registry | **5** |
| ↳ anonymous in registry | 35 |
| Named types in registry | 312 |
| ↳ observed in capture | 5 |
| ↳ NOT observed | 307 |

Replay window is `--replay-max-seq 0xb0 = 176`, which is the last R-direction
message in the capture. The replay therefore covers the entire dump end to
end — there is no tail of "captured but unreplayed" records.

## The five named types we actually see

| Wire | Name | R | W | Notes |
|---|---|---|---|---|
| `0x0003` | RegistrationResponseMsg | 1 | 0 | Server→client V3 accept |
| `0x0013` | RegistrationRequestV3Msg | 0 | 1 | Single send — no retry storm in this capture |
| `0x00a4` | ClientAddEntryMsg | 2 | 0 | Two server-side adds early in flow |
| `0x014f` | TimeSynchMsg | 4 | 0 | Server→client clock sync, 12-byte payload |
| `0x015d` | PingMsg | 10 | 10 | Bidirectional heartbeat, what we now re-send post-replay |

That's it. **Every other top-level wire type in the capture is anonymous** in
the registry — i.e., the type has no `name` field on its reflectable typeinfo
struct.

## What dominates the wire

The capture is overwhelmingly `0x0008` traffic:

```
[anon] 0x0008  R=79  W=0   sizes 78 .. 46423 (median 1013)
```

Cross-referenced against `state-bundles-0x80-0xb0.txt`, `0x0008` is the
**StateBundle channel**: the GridMate replication stream that carries
fragment updates (sub-types `0x4ab`, `0xa`, `0xb72`, `0xc4b`, `0xd`, …,
named in that file as `StateBundleFragment0xNNN`). The remaining anonymous
top-level types (`0x1b88`, `0x18a6`, `0x16a0`, `0x065c`, …) are the
heavyweight peers — the largest single record is a 99 819-byte `0x16a0`,
followed by a 46 423-byte `0x0008`. These are almost certainly the
chunked, MF_CHUNK-fragmented bulk payloads we already ship via
`replay_chunking_design.md`.

## What this means for the state-10→11 hypothesis

`docs/next-session.md` lists `SpawnActorsMsg=0x23e` as a candidate
"spawn trigger" not present in the replay. Confirmed: type 574
(0x23e) appears nowhere in the capture. **But that observation is
weaker than it looks**:

- The named, top-level wire types we see in the capture are
  exclusively control-plane (auth, ping, time-sync, RPC entry).
- The actual world state — the actors, fragments, replication
  updates — rides inside `0x0008` as anonymous StateBundle
  fragments. A real client session that *did* go in-world wrote
  zero `SpawnActorsMsg=0x23e` packets at the top level.
- 307/312 named registry types are unobserved. That includes every
  `MoveAnActorMsg`, `CommitMovementMsg`, `AddActorMessage`,
  `SpawnActorsMsg`, etc. You wouldn't expect them on the wire as
  top-level messages — they are fragment-embedded RPCs.

**Implication:** the state-10→11 advance gate is unlikely to be "send a
specific named top-level message we forgot." It's more likely:
  1. A property *inside* the StateBundle fragments (the `0x0008` stream)
     that the wrapper-tick polls — already shipped via replay; therefore
     a substitution / decoding bug, not a missing message; or
  2. A handshake we owe at the Carrier layer (ACK / reliable seq) that
     the live-server provides automatically and our replay does not; or
  3. A timing constraint — fragments must arrive in <T after V3 accept,
     and our replay is too slow / too fast.

This argues strongly for the **Carrier-ACK experiment** (the 5-line
piggyback already shipped for V3 generalised to all reliable channels)
and for **per-fragment timing comparison** between live and replay,
rather than for hunting the next named message to send.

## Categorised list of unobserved named types

For reference when looking for a specific RPC name. (Full list in the
output of `tools/typeregistry_diff.py`.)

- **world/actor (58)** — `SpawnActorsMsg`, `MoveAnActorMsg`,
  `AddActorMessage`, `ReceiveActorMsg`, `ActorInitializedMessage`,
  `SpawnRestoredSpatialActorMsg`, …
- **chat / persistence (35)** — `GameChatMessage`, `BaseGameChatMessage`,
  `PrepareMoveMessage`, `ResolveMoveMessage`, persistence save/restore.
- **misc Msg (99)** — every Init/Update/Add/Remove of registry, hub,
  routing, fragments — entirely the "control plane that the live server
  manages on its end", not the wire.
- **movement (8)** — `CommitMovementMsg`, `AckMovementMsg`,
  `AbortMovementMsg`, …
- **keepalive (8)** — `PingTrait`, `PingResponseMsg`, `SendClockSyncMsg`,
  `TimeoutMigrationsMsg`. Note `PingMsg=0x3f0` (1008) in addition to the
  observed `PingMsg=0x15d` (349) — there are two distinct PingMsgs in the
  registry on different typeIndexes.
- **territory/zone (7)** — entirely cross-world reconnect machinery.
- **auth/session (5), quest (12), rpc (6), other (68)** — see
  `python tools/typeregistry_diff.py` for the full enumeration.

## Operational notes for future captures

- A capture that loses no top-level wire types vs. ours would still be
  worth shipping — what changes will be the *fragment composition inside
  `0x0008`*, which is exactly where the spawn / movement / combat data
  lives.
- `tools/typeregistry_diff.py` accepts `<capture_dir>` and
  `--registry`, so dropping a new capture into `info/<name>/` and running
  the script is a one-liner.
- Two registry types share the name `PingMsg` (`0x15d` and `0x3f0`),
  several `InitMsg`/`UpdateMsg` collisions exist. When matching by name,
  always disambiguate by typeIndex.
