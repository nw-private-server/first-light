# Capture Routes Audit

This file records the current state of the repo's DTLS/Javelin capture and
decryption options after the live EAC path blocked the obvious runtime bypasses.

## Current ranking

1. **Offline `pcapng` analysis**
   - Status: best current route
   - Why: we already have real AWS-side DTLS captures and can isolate the stable
     encrypted REP registration window without touching the live client.
   - Limits: no session secrets yet, so this yields timing/size/protocol-shape
     information rather than decrypted Javelin payloads.

2. **Transport-only capture**
   - Status: useful for metadata only
   - Tools: `tools/dtls_intercept.py`, `tools/udp_probe.py`
   - Why: these are still useful for raw DTLS record timing, lengths, endpoints,
     and sequence behavior.
   - Limits: they do not decrypt DTLS application data.

3. **SSLKEYLOGFILE**
   - Status: blocked in the current repo state
   - Evidence: there are no non-empty `sslkeys.log`, `CLIENT_RANDOM`, or other
     keylog artifacts under `capture/`.
   - Interpretation: `tools/capture_session.py` sets `SSLKEYLOGFILE`, but the
     current game/runtime path did not emit reusable secrets.

4. **Frida/OpenSSL hook**
   - Status: blocked on the live client
   - Evidence:
     - stored hook attempt at `capture/20260416_224201_dtls_test/hooks.log`
       failed because `SSL_read` was not found
     - live Frida attach later failed with `VirtualAllocEx` `ACCESS_DENIED`
   - Interpretation: this may still be viable on a non-EAC-friendly target, but
     it is not currently workable against the live process.

5. **Local DTLS MITM proxy**
   - Status: blocked on the live client
   - Tools: `tools/dtls_proxy.py`, `tools/udp_redirect.py`
   - Evidence: the client reaches a real DTLS handshake against the probe, then
     aborts with fatal `unknown ca`
   - Interpretation: the remaining problem is certificate trust, not queue/auth.
     Without a trust bypass or a target that accepts our cert, this route cannot
     yield decrypted Javelin traffic.

## Practical conclusion

There is **no already-working non-EAC decryption path in the repo today**.

The most realistic path forward is:

1. keep using the offline `pcapng` captures to narrow the earliest encrypted REP
   registration/bootstrap records we care about
2. find a non-EAC-friendly environment or another source of session secrets
3. then use those secrets to decrypt the already-isolated registration window

## Tooling

Use:

```powershell
python tools/assess_capture_routes.py
```

to print the current route assessment directly from repo state.
