# Login/Spawn Handoff Notes

This export covers `0x0..0xb0` from `resources/captures/nw-3-26/messages/20260502-153840`.
It is the post-Carrier message stream, not the UDP Carrier handshake text.

## Sequence Map

| seq | dir | type | why it matters |
| --- | --- | --- | --- |
| `0x0` | `W` | `0x13` | `RegistrationRequestV3Msg`; sensitive values are redacted in the dump. |
| `0x1` | `R` | `0x3` | Registration response. |
| `0x2..0x24` | mixed | mixed | Early setup/control traffic and ping traffic. |
| `0x25` | `R` | `0x8` | First large StateBundle unit, about 46 KB. This burst is mandatory. |
| `0x29` | `R` | `0x16a0` | Large init payload, about 99 KB. |
| `0x2a..0x6c` | mostly `R` | `0x8` | Repeated large StateBundle init units, about 46 KB each. |
| `0x73..0x7f` | `R` | `0x8` | Smaller StateBundle records after the big init burst. |
| `0x80` | `R` | `0x8` | StateBundle summary reports `state=13`; this matches the WaitingForPlayerSpawn gate area. |
| `0x8c` | `R` | `0x8` | StateBundle summary reports `state=25`, `interest=91`, 13 fragments. This is one of the important local-player/self-identification comparison points. |
| `0x91` | `R` | `0x8` | StateBundle summary reports `state=28`, `interest=92`, only fragment `0x108c`. |
| `0xae` | `R` | `0x8` | StateBundle summary repeats the `interest=91` fragment set at later state `51`. |
| `0xb0` | `R` | `0x8` | StateBundle summary reports `state=53`; by this point this capture has advanced past the state-13 stall area. |

## isMasterPlayer Without a DLL Patch

Treat `isMasterPlayer=0` as a symptom, not the packet to spoof directly. The DLL patch works because it bypasses the client-side predicate/dispatch gate, but the wire-side fix should be to send the server-originated StateBundle path that makes the local player actor resolve as the client's owned/master actor.

The comparison window is `0x80..0xae`, not the Carrier connect ACK. In this capture:

- `0x80_T0x8_R.bin` enters the `state=13` area.
- `0x8c_T0x8_R.bin` carries `interest=91` with fragments `0xf5f`, `0x108c`, `0xc4b`, `0x130e`, `0x25b`, `0xb`, `0xc50`, `0x383`, `0x5f8`, `0xa`, `0xcf0`, `0x15f4`, and `0xc6f`.
- `0xae_T0x8_R.bin` repeats the same `interest=91` fragment set after the client has advanced further.

If another implementation reaches `WaitingForPlayerSpawn` and needs to force `isMasterPlayer=1`, it is likely missing or mis-keying the local-player ownership/self-identification StateBundle record. Check that the same player identity/session/actor continuity survives across registration, the early `0x65c` response, the large StateBundle init burst, and the `interest=91` StateBundle records.

The practical diff target is:

1. Match the order and presence of the large `0x8` init burst through `0x6c`.
2. Compare their `0x80..0xae` StateBundle summaries against `state-bundles-0x80-0xb0.txt`.
3. If `interest=91` or its fragment set is absent, keyed to the wrong actor/session, or sent before the local actor exists, the client can stay in the non-master dispatch path.
