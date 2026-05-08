/**
 * Frida hook on PlayerManagerSelfIdentification handler.
 *
 * Hooks FUN_146454c00 (RVA 0x06454c00) at entry, logs seven in-args
 * each time it fires. Designed to resolve two questions left open by
 * static-RE:
 *
 *   1. Does the handler fire at all during a replay-substitute session?
 *      If never → the captured replay genuinely lacks the gating
 *      message and the project needs new captures.
 *      If yes → static-RE interpretation B is correct (the captured
 *      seq 0x7 type-0x651 message IS SelfIdent for this build, just
 *      with sub-byte 0x19 instead of community-dump's 0x17), and the
 *      state-10 stall is from substitution / seq ordering / ack
 *      shape rather than missing message.
 *
 *   2. What are the actual byte layouts of the seven in-args? Static
 *      RE established the call signature
 *        PlayerManagerSelfIdentification(
 *          GameConnection*, ?, Tuple36*, Tuple36*, ?, MsgBody*,
 *          StringPlus17*)
 *      but byte-precise field shapes need runtime data. This hook
 *      captures all seven args and dumps the structs they point to.
 *
 * Background: see analysis/state_machine_summary.md § "The single
 * direct caller = PlayerManagerSelfIdentification" and
 * analysis/proposed_patches/correlation_echo_v3_response.md for the
 * companion server-side experiment.
 *
 * Usage:
 *   Load via frida-cli or the project's frida_capture.py:
 *
 *     frida -p <NewWorld_PID> -l tools/client-hooks/frida_self_ident_hook.js
 *
 *   Or add to frida_capture.py's script-loading list. Output is sent
 *   to the standard {type:"log", text:...} channel, so it shows up
 *   alongside the main DTLS hook logs.
 *
 * What "success" looks like:
 *   - On a normal replay session, look for "[selfident] HANDLER FIRED"
 *     log lines.
 *   - The log shows the seven arg pointers and a hex dump of the
 *     bytes at param_3, param_4, param_6, and param_7 (the structs).
 *   - If nothing fires: the captured replay isn't delivering the
 *     gating message — switch to extending the capture window or
 *     trying the correlation-echo patch first.
 */

"use strict";

// ---------------------------------------------------------------------------
//  Constants
// ---------------------------------------------------------------------------

// Function RVAs from static RE (image base = 0x140000000 in the live
// Steam build downloaded 2026-05-06).
var INTERNAL_RVA_SELF_IDENT_HANDLER = 0x06454c00;  // FUN_146454c00
var INTERNAL_RVA_ON_CONNECTION_SUCCESS = 0x05a87010;  // FUN_145a87010

// How many bytes to hex-dump from each pointer-shaped arg. Tunable
// based on the static field-shape estimates in analysis/state_machine_summary.md.
var DUMP_BYTES_TUPLE36 = 36;       // param_3, param_4 -- 36-byte tuples
var DUMP_BYTES_MSGBODY = 32;        // param_6 -- 28-byte header + slack
var DUMP_BYTES_STRING_PLUS_17 = 48; // param_7 -- AZStd::string + 17-byte tail

var hookCount = 0;
var connectionSuccessCount = 0;

// ---------------------------------------------------------------------------
//  Helpers
// ---------------------------------------------------------------------------

function log(msg) {
    send({ type: "log", text: "[selfident] " + msg });
}

function safeReadHex(ptrVal, n) {
    if (ptrVal.isNull()) {
        return "<null>";
    }
    try {
        var bytes = ptrVal.readByteArray(n);
        if (!bytes) {
            return "<unreadable>";
        }
        var arr = new Uint8Array(bytes);
        var hex = [];
        for (var i = 0; i < arr.length; i++) {
            hex.push(("0" + arr[i].toString(16)).slice(-2));
        }
        return hex.join(" ");
    } catch (e) {
        return "<err: " + e.message + ">";
    }
}

function dumpAzStdString(ptrVal) {
    // AZStd::string layout: [data ptr or inline 16B][size:8][capacity:8]
    // SSO threshold: if capacity > 0xf, data is heap-allocated and
    // *string == data ptr; otherwise the bytes ARE the inline storage.
    if (ptrVal.isNull()) return "<null-string>";
    try {
        var capacity = ptrVal.add(24).readU64();
        var size = ptrVal.add(16).readU64();
        var dataPtr;
        if (capacity.compare(0xf) > 0) {
            dataPtr = ptrVal.readPointer();
        } else {
            dataPtr = ptrVal;
        }
        var sizeNum = size.toNumber();
        if (sizeNum > 0 && sizeNum < 1024) {
            var str = dataPtr.readUtf8String(sizeNum);
            return JSON.stringify(str) + " (size=" + sizeNum +
                   ", cap=" + capacity.toString() + ")";
        }
        return "<size=" + sizeNum + ", cap=" + capacity.toString() + ">";
    } catch (e) {
        return "<err: " + e.message + ">";
    }
}

// ---------------------------------------------------------------------------
//  Hook installation
// ---------------------------------------------------------------------------

function installHooks() {
    var mainModule = Process.enumerateModules()[0];
    if (!mainModule) {
        log("ERROR: no module found");
        return;
    }
    var base = mainModule.base;
    log("base=" + base + " name=" + mainModule.name);

    // Hook 1: the SelfIdent handler entry.
    var selfIdentAddr = base.add(INTERNAL_RVA_SELF_IDENT_HANDLER);
    Interceptor.attach(selfIdentAddr, {
        onEnter: function (args) {
            hookCount++;
            log("HANDLER FIRED #" + hookCount);
            log("  param_1 (GameConnection*) = " + args[0]);
            log("  param_2                  = " + args[1]);
            log("  param_3 (Tuple36*)       = " + args[2] +
                "   bytes: " + safeReadHex(args[2], DUMP_BYTES_TUPLE36));
            log("  param_4 (Tuple36*)       = " + args[3] +
                "   bytes: " + safeReadHex(args[3], DUMP_BYTES_TUPLE36));
            log("  param_5                  = " + args[4]);
            log("  param_6 (MsgBody*)       = " + args[5] +
                "   bytes: " + safeReadHex(args[5], DUMP_BYTES_MSGBODY));
            log("  param_7 (StringPlus17*)  = " + args[6]);
            log("  param_7 string content: " + dumpAzStdString(args[6]));
            log("  param_7 raw bytes: " + safeReadHex(args[6], DUMP_BYTES_STRING_PLUS_17));
        }
    });
    log("hooked SelfIdent handler at " + selfIdentAddr);

    // Hook 2: onConnectionSuccess (the wrapper-substate writer).
    // If this fires, state 10 → 11 advance is happening. If the SelfIdent
    // handler fires but onConnectionSuccess doesn't, the handler is
    // bailing somewhere mid-execution (substitution / type mismatch).
    var ocsAddr = base.add(INTERNAL_RVA_ON_CONNECTION_SUCCESS);
    Interceptor.attach(ocsAddr, {
        onEnter: function (args) {
            connectionSuccessCount++;
            log("onConnectionSuccess FIRED #" + connectionSuccessCount +
                "  wrapper=" + args[0]);
        }
    });
    log("hooked onConnectionSuccess at " + ocsAddr);

    log("READY -- waiting for handlers to fire");
}

// ---------------------------------------------------------------------------
//  Entry point
// ---------------------------------------------------------------------------

setTimeout(installHooks, 0);
