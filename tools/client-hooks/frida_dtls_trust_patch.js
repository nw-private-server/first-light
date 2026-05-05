"use strict";

// Runtime-only DTLS trust bypass for New World.
//
// Target: Javelin_SecureSocketDriver_Initialize (FUN_145dce750), RVA 0x5dce750.
//
// Approach: hook the function's entry and zero param_1[0x51] (the verifyField
// pointer at ctx+0x288) BEFORE the body runs. The function then evaluates its
// own `if (ca_bundle_slot == 0)` test as true and naturally takes the
// permissive branch, which registers the always-accept callback at
// FUN_1402a1a70. No code-flow rewrite, so the rest of the function body
// (shared setup past the JZ) runs unchanged.
//
// An earlier version of this script rewrote the JZ at 0x145dce8b5 into an
// unconditional JMP. That forced the branch taken but left the SSL_CTX in a
// half-initialized state (the strict branch's CA-list setup was never run,
// while verifyField was still non-null), and the client created the UDP
// socket but never emitted ClientHello before the process died. Nulling the
// field and letting the function decide the branch itself avoids that hazard.

const RVA_SECURE_INIT = 0x5dce750;
const VERIFY_FIELD_OFFSET = 0x288;

function sendLog(text) {
    send({ type: "log", text: text });
}

function fail(text) {
    send({ type: "status", ok: false, text: text });
}

function ok(text) {
    send({ type: "status", ok: true, text: text });
}

function main() {
    const module = Process.enumerateModules()[0];
    const target = module.base.add(RVA_SECURE_INIT);

    sendLog(`module=${module.name} base=${module.base}`);
    sendLog(`secure_init=${target}`);

    try {
        Interceptor.attach(target, {
            onEnter: function (args) {
                const ctx = args[0];
                const verifyPtrSlot = ctx.add(VERIFY_FIELD_OFFSET);
                let before = ptr(0);
                try { before = verifyPtrSlot.readPointer(); } catch (_) {}
                try {
                    verifyPtrSlot.writePointer(ptr(0));
                    sendLog(`[trust-bypass] zeroed verifyField ctx=${ctx} was=${before}`);
                } catch (e) {
                    sendLog(`[trust-bypass] FAILED to null verifyField ctx=${ctx}: ${e}`);
                }
            }
        });
        ok("Installed DTLS trust-bypass onEnter hook on FUN_145dce750");
    } catch (e) {
        fail(`Could not install trust-bypass hook: ${e}`);
    }
}

setImmediate(main);
