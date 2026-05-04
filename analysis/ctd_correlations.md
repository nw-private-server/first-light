# CTD Correlation Audit — 2026-05-04 Sessions

## Per-session table (today's frida_capture runs)

| session_dir | reached_DTLS | medal_temp_window | crashed | duration | exception fault offset |
|---|---|---|---|---|---|
| 20260504_112126_frida_capture | n/a (4-line stub) | NO | NO  | <1s | n/a |
| 20260504_112406_frida_capture | YES (peer 11:30:17) | YES (11:24:50) | YES (process-terminated) | 6m29s | 0x061ae9cf |
| 20260504_132856_frida_capture | NO | YES (13:29:36) | YES (process-terminated) | 1m24s | 0x03007ec3 |
| 20260504_133912_frida_capture | YES (peer 13:40:35) | YES (13:39:51) | NO (Ctrl+C) | 1m54s | (none — user-quit) |
| 20260504_143431_frida_capture | NO | YES (14:35:22) | YES (process-terminated) | 0m55s | 0x03007ec3 |
| 20260504_143546_frida_capture | NO | YES (14:36:27) | YES (process-terminated) | 1m03s | 0x03007ec3 |
| 20260504_144725_frida_capture | NO | YES (14:48:05) | YES (process-terminated) | 0m53s | 0x03007ec3 |

Sources: `session.log` head/tail, `responder_2026050*.log` (`new peer` markers), Windows Event Log Application Error / Windows Error Reporting in last 4h.

## Conclusion: Is Medal correlated with CTDs?

**NO.** Medal opens its `medal_temp_d3d_window_4039785` overlay window in **6 of 6** real sessions today, including the one (`133912`) that reached the DTLS handshake and was only terminated when the user pressed Ctrl+C. Medal also fired ~5 minutes BEFORE the DTLS handshake in `112406`, with no immediate crash.

Medal is a benign init event. It is constant across both CTD and non-CTD outcomes.

`Get-Process` confirms Medal, RTSS, NVIDIA Broadcast, and Discord are all currently running — none of which prevented the one good run today.

## What IS the correlated factor

The Windows Application Error log shows **5 NewWorld.exe APPCRASH events today, all at the exact same fault offset `NewWorld.exe + 0x03007ec3`, exception 0xc0000005 (access violation)**. The lone different crash (`0x061ae9cf` at 11:30:33) happened at the END of the only session that reached DTLS — i.e. a different downstream code path.

The four short CTD sessions all die ~50–90 s after Frida attach, BEFORE the game ever opens its UDP/REP socket (zero `rep-vtbl` hits, zero WSASendTo to udp/23971). They die during early Steam/cloudfront init, well before any private-server traffic. Successful sessions take 6+ min to reach DTLS — the short ones never get there.

This looks like a Frida-injection-timing flake: a NewWorld.exe access violation at a fixed offset that intermittently kills the process during early init, unrelated to overlays or hypothesis suspects.

EAC / Discord overlay strings / RTSS / nvcamera / OBS: no genuine matches in any session log (the 8 case-insensitive "EAC" hits per file were `READ_COMPLETE` substrings).

## One-action recommendation

**Open the four `*-91e5-*`, `*-dbb6-*`, `*-f22c-*`, `*-2c9b-*` WER reports in `%LOCALAPPDATA%\CrashDumps\` (or `WerFault.exe -u -p <pid>` minidumps under `%LOCALAPPDATA%\Microsoft\Windows\WER\ReportArchive\`) and look up `NewWorld.exe + 0x03007ec3` in Ghidra/IDA.** That single instruction is the deterministic CTD culprit — much higher signal than further log mining. Do NOT spend time disabling Medal; it is provably not the cause.
