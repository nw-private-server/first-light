# FAQ

Recurring questions from newcomers. If you've spent more than a few minutes on something that's already answered here, the doc is doing its job.

---

## Q: How do I obtain "a non-EAC build of New World"?

The repo doesn't ship or link one, and the maintainers don't provide a sourcing path. That's deliberate — redistributing a commercial game binary isn't something this project does.

But before you go hunting for one: **most contributors don't actually need it.** The README lists it as a prerequisite because a few specific workflows do, but the common paths don't. Read the next two questions first.

## Q: Do I need the non-EAC build to run the server / connect a client?

No. The live Steam build works for that, using the deployed Frida trust patch.

The reason people assume EAC is a blocker is that EAC prevents Frida from doing in-process hooking (`VirtualAllocEx ACCESS_DENIED` on attach). But the project's DTLS cert-pinning bypass doesn't need deep hooking — it's a 6-byte in-memory patch applied *after EAC has finished initializing but before you click Play*. EAC's scan window has closed by then, so the patch sticks.

How that bypass works (full writeup in [dtls-trust-bypass.md](dtls-trust-bypass.md)):

1. Ghidra decompilation found the cert-validation branch in `FUN_145dce750` (the Javelin DTLS driver init) at VA `0x145dce8b5`. One side of the branch enforces real cert validation against a bundled CA; the other side falls through to a permissive callback (`FUN_1402a1a70`) that just `return 1`s.
2. We flip the conditional `JZ` (`0F 84 19 01 00 00`) to an unconditional `JMP` (`E9 19 01 00 00 90`) so the driver always takes the permissive path.
3. `tools/client-hooks/frida_dtls_trust_patch.py` attaches to a running `NewWorld.exe` and writes those bytes at the right moment.

That's the deployed solution and has been working since 2026-04-19. The live EAC build is fine for running the client against your local mock stack.

## Q: So when *do* I need the non-EAC build?

When you want to **capture decrypted DTLS bytes from inside the client process** — i.e. you're hooking `SSL_read` / `SSL_write` (or equivalents) to dump cleartext as the client sees it. That requires Frida to fully attach and instrument arbitrary code, which EAC blocks.

That workflow lives in `tools/client-hooks/frida_capture.py` and the route notes in [non-eac-capture-plan.md](non-eac-capture-plan.md). It's the path used to produce the captures under `info/`.

If you're not doing that, you don't need a non-EAC build. You can:
- Run `auth_mock` and `rep_responder` against the live Steam client with the trust patch.
- Contribute server code, RE work, codec tests, or replay-validation work without ever launching the client at all.

## Q: We don't bypass EAC?

Correct. The project does not bypass EAC. It bypasses **DTLS cert pinning** (Frida runtime patch on the live build), and it sidesteps EAC for one specific workflow (in-process capture) by using a pre-EAC binary instead. Two different problems, two different answers.

Quick reference:

| Problem | Solved by | Works on live EAC build? |
|---|---|---|
| DTLS cert pinning rejects our self-signed cert | Frida runtime patch (Ghidra-derived) | Yes |
| Frida can't hook `SSL_read` for in-process capture | Use archived non-EAC build instead | No — that's the whole reason |

---

If you have a question that took you a while to answer, add it here.
