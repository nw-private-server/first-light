"use strict";

// Runtime-only DTLS trust bypass for New World.
//
// Target:
//   FUN_145dce750
//   0x145dce8b5: JZ permissive_verify_path
//
// Patch:
//   0F 84 19 01 00 00  ->  E9 19 01 00 00 90
//
// This forces the DTLS driver to always jump to the path that calls
// SSL_CTX_set_verify(..., FUN_1402a1a70), where FUN_1402a1a70 simply
// returns 1 (accept any certificate).

function sendLog(text) {
    send({ type: "log", text: text });
}

function fail(text) {
    send({ type: "status", ok: false, text: text });
}

function ok(text) {
    send({ type: "status", ok: true, text: text });
}

const RVA = 0x05dce8b5;
const ORIGINAL = [0x0f, 0x84, 0x19, 0x01, 0x00, 0x00];
const PATCHED  = [0xe9, 0x19, 0x01, 0x00, 0x00, 0x90];

function bytesEqual(a, b) {
    if (a.length !== b.length) return false;
    for (let i = 0; i < a.length; i++) {
        if (a[i] !== b[i]) return false;
    }
    return true;
}

function readBytes(ptr, len) {
    return Array.from(new Uint8Array(Memory.readByteArray(ptr, len)));
}

function main() {
    const module = Process.enumerateModules()[0];
    const target = module.base.add(RVA);
    const before = readBytes(target, ORIGINAL.length);

    sendLog(`module=${module.name} base=${module.base}`);
    sendLog(`target=${target}`);
    sendLog(`before=${before.map(b => b.toString(16).padStart(2, "0")).join(" ")}`);

    if (bytesEqual(before, PATCHED)) {
        ok("DTLS trust patch already applied");
        return;
    }

    if (!bytesEqual(before, ORIGINAL)) {
        fail("Unexpected bytes at DTLS trust patch site; refusing to patch");
        return;
    }

    Memory.protect(target, PATCHED.length, "rwx");
    target.writeByteArray(PATCHED);
    const after = readBytes(target, PATCHED.length);

    sendLog(`after=${after.map(b => b.toString(16).padStart(2, "0")).join(" ")}`);

    if (!bytesEqual(after, PATCHED)) {
        fail("Patch write did not stick");
        return;
    }

    ok("Applied DTLS trust bypass patch");
}

setImmediate(main);
