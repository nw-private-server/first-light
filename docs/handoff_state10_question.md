# NewWorld REP handshake — what we send / what we get / where we're stuck

Binary: `NewWorld.exe` (Steam, pre-shutdown). Image base `0x140000000`. Frida-bypassed cert verify; DTLS terminates fine. Our gateway listens UDP, presents a self-signed cert, ECDHE-RSA-AES256-GCM-SHA384.

## Wire trace (post-DTLS, encrypted Carrier records both ways)

Carrier envelope on every datagram is 4 bytes: `[0x80|0x81] 0x01 [seq_be_u16]`. Bit 0 of byte 0 = encrypted. All inner records are channel-3 SystemMessages.

### Client → us

```
env_seq=2  [sysmsg=1 payload=0000000501]                     [sysmsg=6 payload=2006]
env_seq=3  [sysmsg=1 payload=000000050101]                   [sysmsg=6 payload=2006]
env_seq=4  [sysmsg=1 payload=00000005010101]                 [sysmsg=6 payload=400001000006]
env_seq=5  [sysmsg=1 payload=0000000501010101]               [sysmsg=6 payload=400002000006]
env_seq=6  [sysmsg=1 payload=000000050101010101]             [sysmsg=6 payload=400003000006]
env_seq=7  [sysmsg=6 payload=400004000206]
env_seq=8  [sysmsg=1 payload=00000005010101010101]           [sysmsg=6 payload=400004000306]
...continues forever, sysmsg=1 trailer keeps growing by one 0x01 per retry...
```

### Us → client (best-effort SM_CLOCK_SYNC + SM_CONNECT_ACK pair, channel 3)

```
80 01 0000  b0 00 05 03 00 00 00 00 00 02 04 89  00 05 00 00 00 00 00 05 02
^env hdr    ^SM_CLOCK_SYNC (u32 BE ms + msgId 04)  ^SM_CONNECT_ACK mirror (00000005 + msgId 02)
```

Client never advances. We've cycled 7 ACK shapes (mirror, empty, echo, v0, v3_min, v3_full, dynamic-echo); none make a difference. After ~15s of retry the wrapper times out.

## Where we're stuck (binary side)

This week we got Ghidra to define-as-function the previously-unanalyzed `0x146b6e190` — sole vtable entry for the wrapper's per-tick dispatcher. Decompiled:

```c
void REP_state10_dispatcher(JavelinGameConnectionWrapper *wrapper) {
  GatewayClient *gw = wrapper[0x118];
  if (gw->byte_at_0x160 == 0) {                  // <-- THIS BYTE NEVER FLIPS FOR US
    // BRANCH A — fire small SystemMessage every tick
    int sub = gw->int_at_0x164;
    int msgcode = (sub == 1) ? 6 : (sub == 2) ? 7 : (sub == 3) ? 0xe : 5;
    FUN_146b6c500(wrapper, msgcode, 0, &emptyStr);   // queue-append, SM enqueue
  } else {
    // BRANCH B — build & enqueue RegistrationRequest V2/V3 (selected by global DAT_149f80d34)
    if (DAT_149f80d34 == 0 || stubbedOrDummy()) {
      FUN_146b66a60(buf, ..., w+0x27, +0x39, +0x3d, +0xa2, +0xb2);   // V2, 0x360 bytes
    } else {
      FUN_146b67c70(w+0xed, &cb);                                     // attach callback
      FUN_146b66820(buf, ..., w+0x27, +0x39, +0x3d, +0x7e, +0xa2, +0xb2);  // V3, 0x470 bytes
    }
    enqueue via wrapper.vtable[0x30];
    wrapper[0x600] = 0;
  }
}
```

So our captured `00 00 00 05 01...` bytes are BRANCH A — **the client is just spinning, sending a SystemMessage tick because `gw[0x160]` is still 0**. The actual `RegistrationRequestV3Msg` builder (`FUN_146b66820`, 0x470 bytes — confirmed against your typeregistry where `CreateInstance` opcode bytes encode `b9 70 04 00 00 00` = `MOV ECX, 0x470`) is **never called**.

## Hypothesis (where your typeregistry pointed us)

The REP cluster in your dump (indices 70-81) lines these up next to each other:

| idx | name                       | size  | guid                                  |
|-----|----------------------------|-------|---------------------------------------|
| 72  | TimeSynchMsg               | 0x10  | 038CD847-0653-4243-9A26-936E3BD7F312 |
| 73  | RegistrationResponseMsg    | 0x60  | 104145A7-FF95-44F1-9468-21FB41C8AC2B |
| 74  | PingMsg                    | 0x10  | 6A379FB8-0BDD-43A1-AB3E-9843D7BE8CD3 |
| 75  | RegistrationRequestMsg V1  | 0x320 | 8673A3CC-2848-4C87-AA72-CC860589D1B5 |
| 76  | RegistrationRequestV2Msg   | 0x360 | DA4E5889-A65C-4480-8642-0278160125A7 |
| 77  | RegistrationRequestV3Msg   | 0x470 | 0B826B33-89F5-49E0-B8CB-FE4433427778 |
| 80  | **ClientConnectionMsg**    | **0x690** | C4F1E7B5-D502-49F4-AC71-27928C9D25C5 |
| 81  | ClientDisconnectionMsg     | 0x690 | CABD72FF-CCA0-4C8A-804E-C585B386DCFE |

`ClientConnectionMsg` (0x690 = 1680 bytes) being so big and shipping symmetrically with `ClientDisconnectionMsg` smells like **the unsolicited server→client message that brings the session up**. We think the actual sequence is:

1. DTLS up ✅
2. **Server sends ClientConnectionMsg (we don't do this)** — its handler likely writes `gw[0x160]`, sets the sub-state at `+0x164`, and seeds whatever else the client needs
3. Client now takes BRANCH B and emits `RegistrationRequestV3Msg` (which would be the *first* time we see registration bytes from it — we never have)
4. We respond with `RegistrationResponseMsg` (0x60 bytes — error_code at +0x08 must be 0; eos_flag at +0x5b must be 0; session_token AZStd::string at +0x18; status bytes at +0x58/+0x59/+0x5a)
5. Client transitions state-10 → state-11

If this is right, we've been trying to skip steps 2-3 and the whole `00 00 00 05 01...` chatter we've been agonizing over is just the client politely waiting.

## Update — found the exact setter; ClientConnectionMsg hypothesis was wrong

After more digging in the binary, **we found the function that flips `gw[0x160] = 1`**. It's `FUN_146b713e0` (122 bytes, sole purpose):

```c
void state_handler(state_ctx, void **msg_ptr_ptr) {
    msg = *msg_ptr_ptr;
    gw  = state_ctx[+8];
    gw[0x164] = (*msg->vtable[0x20])(msg);     // store sub-state code
    if ((*msg->vtable[0x8])(msg)) {            // predicate
        gw[0x160] = 1;                          // <-- THE FLIP
        // attach callback {vtable=PTR_LAB_148591708, gw_ptr}, forward
        (*msg->vtable[0x48])(msg, &callback);
    }
    if (gw[0xa8]) gw[0xa8].vtable[0x10]();     // notify observer
}
```

Two DATA xrefs:
- `0x14ac16ff4` — slot in the wrapper's state-method table (REP_state10_dispatcher is in the same table at `0x14ac16f44`)
- `0x1485916b8` — slot in another vtable

So `FUN_146b713e0` is **invoked via vtable when the wrapper receives a specific message from the server**. The message must:
- Be the type that gets routed to this state-method (so `ClientConnectionMsg` was the wrong guess — that's client→server)
- Have a vtable where slot `[0x8]()` returns true for our case
- Have slot `[0x20]()` return a non-zero code (which lands in `gw[0x164]` and picks the BRANCH A msgcode 6/7/14, not 5 — so somewhere in {1, 2, 3})

## What we'd love from you

1. **Which message type is `FUN_146b713e0` registered to handle?** The state-method table is at `NewWorld+0xac16f00..0xac17040`-ish (RVAs); `FUN_146b713e0` is at the slot containing offset `0x4ff4` from base `0x14ac16f00`. If you have the wrapper's vtable mapped to message types in your impl, knowing which message-type triggers this slot would unblock us today.
2. **What does `vtable[0x8]()` need to return true?** I.e., what minimal payload satisfies the predicate?
3. **Three protocol layers above DTLS** you mentioned — is the layering: Carrier datagram envelope → Carrier system-message channel (msgId 1/2/4/6/etc) → GridMate registry-keyed payloads? Or are there other tiers we haven't seen?
4. **Channel 3 sysmsg=6 with payloads `2006`, `400001000006`, `400003000006`** — is that an ack-list (`40` flag, `seq_be_u16`, `00 00`, `06` = msgId)? We've been treating it as opaque.
5. **The `00000005` prefix** in BRANCH A — is `0x05` a SystemMessage opcode in your map (separate from the GridMate registry-index space)?

Repo (private, can grant access): https://github.com/L3G/NWPrivateServer
DTLS responder: `server/rep_responder.py`. Carrier marshalling: `server/javelin/frame.py`. Symbols + our partial Ghidra DB: happy to share.
