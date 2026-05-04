# Frida Hook CTD Audit — `tools/frida_dtls_hook.js`

Audit of suspicious patterns most likely to cause the intermittent ~30-90s
character-select CTD. Sorted by suspicion.

---

## 1. `correlateSocketWithRep` → `scanRepSocketRefs` race + huge unguarded scan
**Location:** `tools/frida_dtls_hook.js:430-494` (esp. `scanObjectForSocketRef`
loop @ 436-451 and `scanRepSocketRefs` @ 466-473)

**Trigger:** Called from `WSASend` onEnter (line 1813), `WSARecv`
onEnter+onLeave (1840, 1843). These fire on Winsock IOCP/worker threads.

**Why it crashes (high confidence):**
- `currentRepObj` and `currentTransportObj` are **module-level vars** mutated
  by `noteCurrentRepObjects` from the *game-tick thread* (`internal_gameconn_state`,
  `internal_rep_start_helper`).
- `scanObjectForSocketRef` iterates **0x900 bytes / 8 = 288 reads** for the rep
  object, **0x300/8 = 96 reads** for the transport, plus 5 more sub-object
  scans of 0x300 bytes each — every single WSASend/WSARecv on a UDP socket
  walks ~768 pointer reads off `currentRepObj` / `currentTransportObj`.
- The reads are done on the IOCP thread, but the pointers can be freed/realloc'd
  by the game thread between `if (basePtr.isNull())` (line 431) and the loop
  body. `safeReadPtrValue` swallows access faults, **but Frida's exception-handler
  fault path is not race-safe**: if the page is unmapped *during* the SEH
  unwind, the host process eats an unhandled SEGV.
- Even when caught, the cost of 100s of expected-to-fault reads per packet on a
  hot path is huge — and at character-select the game ramps UDP traffic 10-50x.
  This explains the timing-correlation (30-90s after launch) and the ~50% rate
  (depends whether the realloc happens during a packet vs. between packets).

**Confidence:** HIGH

**Patch:**
```diff
@@ function scanRepSocketRefs(sock) {
-    addScan("rep", currentRepObj, 0x900);
-    addScan("transport", currentTransportObj, 0x300);
-
-    try { addScan("rep+0xd0", currentRepObj.add(0xd0).readPointer(), 0x300); } catch (_) {}
-    try { addScan("rep+0x118", currentRepObj.add(0x118).readPointer(), 0x300); } catch (_) {}
-    try { addScan("transport+0x60", currentTransportObj.add(0x60).readPointer(), 0x300); } catch (_) {}
-    try { addScan("transport+0x68", currentTransportObj.add(0x68).readPointer(), 0x300); } catch (_) {}
-    try { addScan("transport+0x1b0", currentTransportObj.add(0x1b0).readPointer(), 0x300); } catch (_) {}
+    // Snapshot once -- atomic on x64 reads of aligned pointers.
+    var rep = currentRepObj, tr = currentTransportObj;
+    if (rep.isNull() && tr.isNull()) return results;
+    // Cap scan budget; do NOT chase sub-pointers from another thread.
+    addScan("rep", rep, 0x200);
+    addScan("transport", tr, 0x100);
```
Also disable `correlateSocketWithRep` once a successful correlation has been
logged for a given (sock, rep, transport) triple.

---

## 2. `repWrapperQueueDetailLogged` queue walk — unbounded by-stride pointer add
**Location:** `tools/frida_dtls_hook.js:694-713`

**Trigger:** First fire of vtbl[0x08] of the wrapper-tick object, called every
tick once state==9/10. The walk steps `begin = begin.add(0x40)` while
`begin.compare(end) < 0`.

**Why it crashes (medium confidence):** `begin` and `end` are read off the
this-pointer at offsets +0x38/+0x40 — these may be `unique_ptr<T[]>` start/end,
but the layout was inferred from one observation. If `end < begin` (sentinel
pattern) or `end - begin` is huge (uninitialized debug field), the loop
dereferences `begin.add(0x38).readPointer()` for unmapped memory. The inner
`try { cbObj = begin.add(0x38).readPointer() } catch` will trip Frida's fault
handler on every iteration. Bound by `idx < 4` so it's capped at 4 iterations,
**but the first 1-3 iterations can already AV** if the stride is wrong.

**Confidence:** MEDIUM

**Patch:**
```diff
-                        while (!begin.isNull() && begin.compare(end) < 0 && idx < 4) {
+                        // Bound element-count by computed delta and refuse impossible spans.
+                        var span = end.sub(begin);
+                        if (begin.isNull() || end.isNull() || span.compare(0) <= 0 ||
+                            span.compare(0x400) > 0) { return; }
+                        while (begin.compare(end) < 0 && idx < 4) {
```

---

## 3. `carrierWriteMessages` linked-list walk — next-pointer at offset 0
**Location:** `tools/frida_dtls_hook.js:2922-2944`

**Trigger:** Every send through `Carrier_WriteMessages` (frequent during
DTLS-up state, and ramps at character-select).

**Why it crashes (low-medium confidence):** Linked-list walk
`cur = cur.readPointer()` (line 2944) assumes the next-ptr is at offset 0 of
the `MessageRecord`, but the comment block above says payload is at +0x20 and
seq at +0x1c — there's no documentation in this file confirming the next-ptr
*is* at offset 0. If it's actually a sentinel/back-pointer/refcount the walk
chases a non-pointer value. Loop is bound to 8 iterations per priority queue,
so any single bad chase is contained — but the body reads payload at `cur+0x20`
into a 256-byte `readByteArray` which can fault.

**Confidence:** LOW-MEDIUM (less hot than #1, but adds risk during the same
character-select burst.)

**Patch:**
```diff
-                                        cur = cur.readPointer();
+                                        var next = cur.readPointer();
+                                        // Reject obviously bogus next pointers.
+                                        if (next.isNull() || next.compare(cur) === 0 ||
+                                            next.compare(ptr("0x10000")) < 0) break;
+                                        cur = next;
```

---

## Recommended first action
Disable `correlateSocketWithRep` calls (lines 1813, 1840, 1843) — comment them
out and run a 5-attempt batch. If CTD rate drops from ~50% to <10%, #1 is
confirmed and the patched scan can be re-enabled.
