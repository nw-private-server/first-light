/**
 * Frida DTLS/TLS Hook for New World
 *
 * Intercepts SSL_read / SSL_write (and _ex variants) to capture decrypted
 * traffic from both the DTLS 1.2 game-server channel and the TLS 1.2/1.3
 * HTTPS auth/gateway channel.
 *
 * Because OpenSSL (or BoringSSL) is statically linked into NewWorld.exe,
 * we locate the functions by scanning the main module's export table first,
 * then fall back to signature scanning if exports are stripped.
 *
 * Messages sent to the Python host:
 *   { type: "packet", direction, protocol, len, hexHead, ts, seqNo }
 *     + a binary payload (the full raw buffer)
 *   { type: "log", text }
 *   { type: "hook_status", name, status }  (success / not_found / error)
 */

"use strict";

// ---------------------------------------------------------------------------
//  Globals
// ---------------------------------------------------------------------------

var seqNo = 0;          // monotonic packet counter
var mainModule = null;   // cached Process.enumerateModules()[0]
var sslContextCache = {};  // ptr.toString() -> { protocol: "tls"|"dtls" }
var installedHooks = {};    // hook name -> true
var pendingRetryTimer = null;
var retryDeadline = 0;
var winHttpConnectMap = {}; // HINTERNET connection handle -> { host, port }
var winHttpRequestMap = {}; // HINTERNET request handle -> { host, port, verb, objectName }
var knownUdpSockets = {};   // SOCKET handle string -> { family, type, proto, ts }
var wspHookedPtrs = {};     // provider-level SPI function pointer string -> true
var INTERNAL_RVA_TRANSPORT_CTOR = 0x06b6a270; // FUN_146b6a270
var INTERNAL_RVA_SECURE_INIT = 0x05dce750;    // FUN_145dce750
var INTERNAL_RVA_REP_START_HELPER = 0x06425f20; // FUN_146425f20
var INTERNAL_RVA_GAMECONN_STATE = 0x0644a070;   // FUN_14644a070
var INTERNAL_RVA_REP_READY_SETTER = 0x06b6f190; // FUN_146b6f190
var INTERNAL_RVA_REP_READY_RESET = 0x06b6e7c0;  // FUN_146b6e7c0
var internalRepBacktraceLogged = {
    transportCtor: false,
    secureInit: false,
    repStartHelper: false,
    gameConnState: false,
    repReadySetter: false,
    repReadyReset: false
};
var internalRepDynamicHooks = {}; // hook name -> true
var internalTransportDynamicHooks = {}; // hook name -> true
var gameConnStateLogCount = 0;

// Tunables
var HEX_HEAD_BYTES = 256;

// ---------------------------------------------------------------------------
//  Helpers
// ---------------------------------------------------------------------------

function log(text) {
    send({ type: "log", text: text });
}

function hookStatus(name, status, detail) {
    send({ type: "hook_status", name: name, status: status, detail: detail || "" });
}

function markHook(name) {
    installedHooks[name] = true;
}

function isHooked(name) {
    return installedHooks[name] === true;
}

function toHex(buf, maxLen) {
    var len = Math.min(buf.byteLength, maxLen);
    var hex = [];
    for (var i = 0; i < len; i++) {
        var b = buf[i].toString(16);
        hex.push(b.length < 2 ? "0" + b : b);
    }
    return hex.join(" ");
}

function nowISO() {
    return new Date().toISOString();
}

function ptrKey(ptr) {
    if (ptr === null || ptr === undefined) return "null";
    try {
        return ptr.toString();
    } catch (_) {
        return "invalid";
    }
}

function formatBacktrace(frames) {
    var mod = getMainModule();
    return frames.map(function (addr) {
        try {
            var sym = DebugSymbol.fromAddress(addr);
            var name = (sym && sym.name) ? sym.name : "unknown";
            if (addr.compare(mod.base) >= 0 && addr.compare(mod.base.add(mod.size)) < 0) {
                var rva = addr.sub(mod.base);
                return addr + " [" + mod.name + "+0x" + rva.toString(16) + "] " + name;
            }
            return addr + " " + name;
        } catch (_) {
            return addr.toString();
        }
    }).join(" | ");
}

function rememberUdpSocket(sock, family, type, proto) {
    knownUdpSockets[ptrKey(sock)] = {
        family: family,
        type: type,
        proto: proto,
        ts: nowISO()
    };
}

function isKnownUdpSocket(sock) {
    return knownUdpSockets[ptrKey(sock)] !== undefined;
}

function markWspPtr(ptr) {
    wspHookedPtrs[ptrKey(ptr)] = true;
}

function isWspPtrHooked(ptr) {
    return wspHookedPtrs[ptrKey(ptr)] === true;
}

function markRepDynamicHook(name) {
    internalRepDynamicHooks[name] = true;
}

function isRepDynamicHooked(name) {
    return internalRepDynamicHooks[name] === true;
}

function markTransportDynamicHook(name) {
    internalTransportDynamicHooks[name] = true;
}

function isTransportDynamicHooked(name) {
    return internalTransportDynamicHooks[name] === true;
}

function safeReadPointer(p) {
    try {
        if (p.isNull()) return ptr("0");
        return p.readPointer();
    } catch (_) {
        return ptr("0");
    }
}

function hookRepVirtualMethod(repObj, byteOffset, hookName, label) {
    if (repObj.isNull() || isRepDynamicHooked(hookName)) {
        return;
    }
    try {
        var vtbl = safeReadPointer(repObj);
        if (vtbl.isNull()) {
            return;
        }
        var target = safeReadPointer(vtbl.add(byteOffset));
        if (target.isNull()) {
            return;
        }
        Interceptor.attach(target, {
            onEnter: function (args) {
                this.thisPtr = args[0];
                try {
                    var transportObj = this.thisPtr.add(0x118).readPointer();
                    hookTransportObjectVirtuals(transportObj);
                } catch (_) {}
                var extra = "";
                try {
                    extra = " state=" + describeRepState(this.thisPtr);
                } catch (_) {}
                log("[rep-vtbl] " + label + " enter this=" + this.thisPtr +
                    " target=" + target + extra);
            },
            onLeave: function (retval) {
                try {
                    var transportObj = this.thisPtr.add(0x118).readPointer();
                    hookTransportObjectVirtuals(transportObj);
                } catch (_) {}
                var extra = "";
                try {
                    extra = " state=" + describeRepState(this.thisPtr);
                } catch (_) {}
                log("[rep-vtbl] " + label + " leave ret=" + retval +
                    " target=" + target + extra);
            }
        });
        markRepDynamicHook(hookName);
        hookStatus(hookName, "success", target.toString());
        log("[rep-vtbl] hooked " + label + " at " + target +
            " (slot +" + byteOffset.toString(16) + ")");
    } catch (e) {
        hookStatus(hookName, "error", e.toString());
    }
}

function hookRepObjectVirtuals(repObj) {
    if (repObj.isNull()) {
        return;
    }
    hookRepVirtualMethod(repObj, 0x08, "internal_rep_vtbl_08", "rep.vtbl+0x08");
    hookRepVirtualMethod(repObj, 0x10, "internal_rep_vtbl_10", "rep.vtbl+0x10");
    hookRepVirtualMethod(repObj, 0x18, "internal_rep_vtbl_18", "rep.vtbl+0x18");
    hookRepVirtualMethod(repObj, 0xa8, "internal_rep_vtbl_a8", "rep.vtbl+0xa8");
}

function describeTransportState(transportObj) {
    function rb(off) {
        try { return transportObj.add(off).readU8(); } catch (_) { return -1; }
    }
    function rd(off) {
        try { return transportObj.add(off).readU32(); } catch (_) { return -1; }
    }
    function rp(off) {
        try { return transportObj.add(off).readPointer(); } catch (_) { return ptr("0"); }
    }
    return "{60=" + rp(0x60) +
        ",68=" + rp(0x68) +
        ",164=" + rd(0x164) +
        ",168=" + rb(0x168) +
        ",169=" + rb(0x169) +
        ",16a=" + rb(0x16a) +
        ",1b0=" + rp(0x1b0) + "}";
}

function hookTransportVirtualMethod(transportObj, byteOffset, hookName, label) {
    if (transportObj.isNull() || isTransportDynamicHooked(hookName)) {
        return;
    }
    try {
        var vtbl = safeReadPointer(transportObj);
        if (vtbl.isNull()) {
            return;
        }
        var target = safeReadPointer(vtbl.add(byteOffset));
        if (target.isNull()) {
            return;
        }
        Interceptor.attach(target, {
            onEnter: function (args) {
                this.thisPtr = args[0];
                var extra = "";
                try {
                    extra = " state=" + describeTransportState(this.thisPtr);
                } catch (_) {}
                log("[rep-transport] " + label + " enter this=" + this.thisPtr +
                    " target=" + target + extra);
            },
            onLeave: function (retval) {
                var extra = "";
                try {
                    extra = " state=" + describeTransportState(this.thisPtr);
                } catch (_) {}
                log("[rep-transport] " + label + " leave ret=" + retval +
                    " target=" + target + extra);
            }
        });
        markTransportDynamicHook(hookName);
        hookStatus(hookName, "success", target.toString());
        log("[rep-transport] hooked " + label + " at " + target +
            " (slot +" + byteOffset.toString(16) + ")");
    } catch (e) {
        markTransportDynamicHook(hookName);
        hookStatus(hookName, "error", e.toString());
    }
}

function hookTransportObjectVirtuals(transportObj) {
    if (transportObj.isNull()) {
        return;
    }
    hookTransportVirtualMethod(transportObj, 0x08, "internal_transport_vtbl_08", "transport.vtbl+0x08");
    hookTransportVirtualMethod(transportObj, 0x20, "internal_transport_vtbl_20", "transport.vtbl+0x20");
    hookTransportVirtualMethod(transportObj, 0x30, "internal_transport_vtbl_30", "transport.vtbl+0x30");
    hookTransportVirtualMethod(transportObj, 0x48, "internal_transport_vtbl_48", "transport.vtbl+0x48");
    hookTransportVirtualMethod(transportObj, 0x68, "internal_transport_vtbl_68", "transport.vtbl+0x68");
    hookTransportVirtualMethod(transportObj, 0x80, "internal_transport_vtbl_80", "transport.vtbl+0x80");
}

function describeRepState(repObj) {
    function rb(off) {
        try { return repObj.add(off).readU8(); } catch (_) { return -1; }
    }
    function rp(off) {
        try { return repObj.add(off).readPointer(); } catch (_) { return ptr("0"); }
    }
    return "{600=" + rb(0x600) +
        ",601=" + rb(0x601) +
        ",6f0=" + rb(0x6f0) +
        ",6f1=" + rb(0x6f1) +
        ",6f2=" + rb(0x6f2) +
        ",d0=" + rp(0xd0) +
        ",118=" + rp(0x118) + "}";
}

// ---------------------------------------------------------------------------
//  SSL object inspection
// ---------------------------------------------------------------------------

/**
 * Determine whether an SSL* object is running DTLS or TLS.
 *
 * Strategy:
 *   1. Call SSL_version(ssl) if we found the export.  DTLS 1.2 = 0xFEFD,
 *      TLS 1.2 = 0x0303, TLS 1.3 = 0x0304.
 *   2. Fall back to calling SSL_get_session / SSL_SESSION_get_protocol_version
 *      which BoringSSL also exposes.
 *   3. Failing that, heuristic: read the 2-byte version field that typically
 *      sits at offset +0 of the SSL3_STATE sub-structure.
 *
 * We cache results per SSL* pointer so the probe only runs once.
 */

var _SSL_version = null;  // resolved later
var _GetLastError = null;

try {
    _GetLastError = new NativeFunction(
        Module.getExportByName("kernel32.dll", "GetLastError"),
        "uint32",
        []
    );
} catch (_) {
    _GetLastError = null;
}

function classifySSL(sslPtr) {
    var key = sslPtr.toString();
    if (sslContextCache[key] !== undefined) {
        return sslContextCache[key];
    }

    var protocol = "unknown";

    if (_SSL_version !== null) {
        try {
            var ver = _SSL_version(sslPtr);
            if (ver === 0xFEFD || ver === 0xFEFF) {
                protocol = "dtls";
            } else if (ver >= 0x0300 && ver <= 0x0304) {
                protocol = "tls";
            } else {
                protocol = "ssl_ver_0x" + ver.toString(16);
            }
        } catch (e) {
            protocol = "unknown";
        }
    }

    // If still unknown, try reading the version field from the structure.
    // In both OpenSSL and BoringSSL, ssl->version is an int at a small offset
    // near the top of the struct. Common offsets: 0 (BoringSSL), 0 (OpenSSL 1.1+).
    if (protocol === "unknown") {
        try {
            var ver = sslPtr.readU16();
            if (ver === 0xFEFD || ver === 0xFEFF) {
                protocol = "dtls";
            } else if (ver >= 0x0300 && ver <= 0x0304) {
                protocol = "tls";
            }
        } catch (_) { /* swallow access violation */ }
    }

    var result = { protocol: protocol };
    sslContextCache[key] = result;
    return result;
}

// ---------------------------------------------------------------------------
//  Core interceptor factory
// ---------------------------------------------------------------------------

/**
 * Build an Interceptor.attach spec for an SSL_read or SSL_write style function.
 *
 * @param {string} name   Human-readable name (e.g. "SSL_read")
 * @param {string} dir    "read" or "write"
 * @param {boolean} isEx  true for _ex variants (extra out-param for bytes moved)
 */
function makeInterceptor(name, dir, isEx) {
    return {
        onEnter: function (args) {
            this.ssl  = args[0];
            this.buf  = args[1];
            this.num  = args[2].toInt32();
            if (isEx) {
                this.outLen = args[3]; // pointer to size_t written/read
            }
            this.name = name;
            this.dir  = dir;
        },
        onLeave: function (retval) {
            var ret = retval.toInt32();

            // For non-_ex: ret = bytes transferred (or <=0 on error)
            // For _ex:     ret = 1 on success, 0 on error; actual len in *outLen
            var dataLen;
            if (isEx) {
                if (ret !== 1) return;  // error
                try {
                    dataLen = this.outLen.readUInt();
                } catch (_) {
                    dataLen = 0;
                }
            } else {
                if (ret <= 0) return;   // error / want-read / want-write
                dataLen = ret;
            }

            if (dataLen <= 0 || dataLen > 0x1000000) return; // sanity cap at 16 MB

            var info = classifySSL(this.ssl);
            var ts   = nowISO();
            var seq  = seqNo++;

            // Read the actual decrypted bytes from the buffer
            var raw;
            try {
                raw = this.buf.readByteArray(dataLen);
            } catch (e) {
                log("[!] " + this.name + " failed to read buffer: " + e);
                return;
            }

            var hexHead = toHex(new Uint8Array(raw), HEX_HEAD_BYTES);

            send(
                {
                    type:      "packet",
                    direction: this.dir,
                    protocol:  info.protocol,
                    len:       dataLen,
                    hexHead:   hexHead,
                    ts:        ts,
                    seqNo:     seq,
                    hookName:  this.name,
                    sslPtr:    this.ssl.toString()
                },
                raw   // binary payload, received as bytes by Python
            );
        }
    };
}

// ---------------------------------------------------------------------------
//  Module / export resolution
// ---------------------------------------------------------------------------

function getMainModule() {
    if (mainModule !== null) return mainModule;
    var mods = Process.enumerateModules();
    for (var i = 0; i < mods.length; i++) {
        if (mods[i].name.toLowerCase().indexOf("newworld") !== -1) {
            mainModule = mods[i];
            return mainModule;
        }
    }
    // fallback: first module
    mainModule = mods[0];
    return mainModule;
}

function enumerateMainImportsManual() {
    var mod = getMainModule();
    var base = mod.base;
    var imports = [];

    try {
        if (base.readU16() !== 0x5a4d) { // MZ
            return imports;
        }

        var peOff = base.add(0x3c).readU32();
        var pe = base.add(peOff);
        if (pe.readU32() !== 0x00004550) { // PE\0\0
            return imports;
        }

        var coff = pe.add(4);
        var numSections = coff.add(2).readU16();
        var sizeOptHdr = coff.add(16).readU16();
        var opt = coff.add(20);
        var magic = opt.readU16();
        if (magic !== 0x20b) { // PE32+
            return imports;
        }

        var importRva = opt.add(0x78).readU32();
        if (importRva === 0) {
            return imports;
        }

        var sectionTable = opt.add(sizeOptHdr);
        var sections = [];
        for (var i = 0; i < numSections; i++) {
            var s = sectionTable.add(i * 40);
            sections.push({
                va: s.add(12).readU32(),
                vs: s.add(8).readU32(),
                rs: s.add(16).readU32(),
                rp: s.add(20).readU32()
            });
        }

        function rvaToPtr(rva) {
            for (var j = 0; j < sections.length; j++) {
                var sec = sections[j];
                var size = sec.vs > sec.rs ? sec.vs : sec.rs;
                if (rva >= sec.va && rva < sec.va + size) {
                    return base.add(rva);
                }
            }
            return base.add(rva);
        }

        var desc = rvaToPtr(importRva);
        while (true) {
            var originalFirstThunk = desc.readU32();
            var nameRva = desc.add(12).readU32();
            var firstThunk = desc.add(16).readU32();
            if (originalFirstThunk === 0 && nameRva === 0 && firstThunk === 0) {
                break;
            }

            var dllName = "";
            try {
                dllName = rvaToPtr(nameRva).readUtf8String();
            } catch (_) {}

            var thunkRva = originalFirstThunk !== 0 ? originalFirstThunk : firstThunk;
            var thunk = rvaToPtr(thunkRva);
            var iat = rvaToPtr(firstThunk);

            while (true) {
                var entryLow = thunk.readU32();
                var entryHigh = thunk.add(4).readU32();
                if (entryLow === 0 && entryHigh === 0) {
                    break;
                }

                var isOrdinal = ((entryHigh & 0x80000000) !== 0);
                if (!isOrdinal) {
                    var namePtr = rvaToPtr(entryLow).add(2);
                    var symName = "";
                    try {
                        symName = namePtr.readUtf8String();
                    } catch (_) {}
                    if (symName) {
                        var target = null;
                        try {
                            target = iat.readPointer();
                        } catch (_) {}
                        imports.push({
                            dll: dllName,
                            name: symName,
                            iatAddress: iat,
                            address: target
                        });
                    }
                }

                thunk = thunk.add(8);
                iat = iat.add(8);
            }

            desc = desc.add(20);
        }
    } catch (e) {
        log("[!] manual import walk failed: " + e);
    }

    return imports;
}

function findImportedFunction(name) {
    try {
        var manual = enumerateMainImportsManual();
        for (var i = 0; i < manual.length; i++) {
            if (manual[i].name === name && manual[i].address && !manual[i].address.isNull()) {
                log("[*] Resolved import " + name + " via manual IAT to " + manual[i].address +
                    " (slot " + manual[i].iatAddress + ")");
                return manual[i].address;
            }
        }
    } catch (_) {}
    try {
        var imports = Module.enumerateImportsSync(getMainModule().name);
        for (var i = 0; i < imports.length; i++) {
            var imp = imports[i];
            if (imp.type === "function" && imp.name === name && imp.address) {
                log("[*] Resolved import " + name + " via Frida import table to " + imp.address);
                return imp.address;
            }
        }
    } catch (_) {}
    return null;
}

/**
 * Try to resolve a function by name across all loaded modules.
 * Returns NativePointer or null.
 */
function findExport(name) {
    // First try the main module
    var mod = getMainModule();
    var addr = mod.findExportByName(name);
    if (addr !== null) return addr;

    // Try all modules (some DLLs might carry OpenSSL)
    var mods = Process.enumerateModules();
    for (var i = 0; i < mods.length; i++) {
        addr = mods[i].findExportByName(name);
        if (addr !== null) {
            log("[*] Found " + name + " in " + mods[i].name);
            return addr;
        }
    }
    return null;
}

// ---------------------------------------------------------------------------
//  Signature scanning fallback
// ---------------------------------------------------------------------------

/**
 * Signature patterns for SSL_read / SSL_write prologue bytes.
 * These are for MSVC x64 builds of OpenSSL 1.1.x / 3.x / BoringSSL.
 *
 * We search the .text section of NewWorld.exe for these patterns and use
 * cross-references to narrow candidates. This is inherently fragile, so we
 * treat every match as a "candidate" and install the hook anyway -- the worst
 * case is we intercept a wrong function and get garbage (which the Python side
 * can discard).
 */

// OpenSSL 1.1.1+ SSL_read signature hint:
//   The function calls ssl3_read_bytes or dtls1_read_bytes internally.
//   We can search for the string "SSL_read" in .rdata and xref it.
function findByStringXref(funcName) {
    var mod = getMainModule();
    var ranges = mod.enumerateRanges("r--");

    // First, locate the string in read-only data
    var needle = funcName + "\x00";
    var stringAddr = null;
    for (var i = 0; i < ranges.length; i++) {
        var r = ranges[i];
        try {
            var matches = Memory.scanSync(r.base, r.size, stringToPattern(needle));
            if (matches.length > 0) {
                stringAddr = matches[0].address;
                break;
            }
        } catch (_) {}
    }

    if (stringAddr === null) return null;

    // Now scan executable ranges for a LEA that references this string address.
    // LEA RCX, [rip + disp32]:  48 8D 0D xx xx xx xx
    var execRanges = mod.enumerateRanges("r-x");
    for (var i = 0; i < execRanges.length; i++) {
        var r = execRanges[i];
        try {
            var bytes = r.base.readByteArray(r.size);
            if (bytes === null) continue;
            var view = new Uint8Array(bytes);
            for (var j = 0; j < view.length - 7; j++) {
                // 48 8D 0D = lea rcx, [rip+disp32]  or  48 8D 15 = lea rdx, [rip+disp32]
                if (view[j] === 0x48 && view[j+1] === 0x8D &&
                    (view[j+2] === 0x0D || view[j+2] === 0x15)) {
                    var disp = view[j+3] | (view[j+4] << 8) | (view[j+5] << 16) | (view[j+6] << 24);
                    // sign-extend
                    if (disp & 0x80000000) disp = disp - 0x100000000;
                    var target = r.base.add(j + 7 + disp);
                    if (target.equals(stringAddr)) {
                        // Walk backwards to find the function prologue
                        // Common prologues: sub rsp / push rbx / mov [rsp+...]
                        var funcStart = walkBackToPrologue(r.base.add(j));
                        if (funcStart !== null) {
                            log("[*] Found " + funcName + " via string xref at " + funcStart);
                            return funcStart;
                        }
                    }
                }
            }
        } catch (_) {}
    }
    return null;
}

function stringToPattern(str) {
    var hex = [];
    for (var i = 0; i < str.length; i++) {
        var h = str.charCodeAt(i).toString(16);
        hex.push(h.length < 2 ? "0" + h : h);
    }
    return hex.join(" ");
}

function walkBackToPrologue(addr) {
    // Walk back up to 256 bytes looking for common x64 function prologues
    for (var off = 0; off < 256; off++) {
        var p = addr.sub(off);
        try {
            var b0 = p.readU8();
            var b1 = p.add(1).readU8();
            // sub rsp, imm8  =>  48 83 EC xx
            // push rbx       =>  53
            // push rbp       =>  55
            // mov [rsp+..],  =>  48 89 ..
            // int3           =>  CC  (padding before function)
            if (off > 0 && b0 === 0xCC) {
                return p.add(1); // function starts after the padding
            }
            if (b0 === 0x48 && b1 === 0x83) {
                var b2 = p.add(2).readU8();
                if (b2 === 0xEC) return p; // sub rsp, imm8
            }
            if (b0 === 0x48 && b1 === 0x89) {
                // mov [rsp+...], ... -- common first instruction
                // Confirm there's CC or 0x90 or another function-end before this
                if (off > 0) {
                    var prev = p.sub(1).readU8();
                    if (prev === 0xCC || prev === 0xC3 || prev === 0x90) {
                        return p;
                    }
                }
            }
        } catch (_) {}
    }
    return null;
}

// ---------------------------------------------------------------------------
//  O3DE / AzNetworking hooks
// ---------------------------------------------------------------------------

/**
 * Try to hook O3DE's AzNetworking layer.  In the open-source O3DE code:
 *   - AzNetworking::TcpSocket::Send / ::Receive
 *   - AzNetworking::UdpSocket::Send / ::Receive
 *   - AzNetworking::DtlsSocket::Send / ::Receive
 *
 * These are C++ mangled names. We search for partial matches in exports.
 */
function hookAzNetworking() {
    var patterns = [
        "DtlsSocket",
        "UdpSocket",
        "TcpSocket",
        "AzNetworking"
    ];

    var mod = getMainModule();
    var exports;
    try {
        exports = mod.enumerateExports();
    } catch (_) {
        log("[*] Could not enumerate exports of " + mod.name + " for AzNetworking scan");
        return;
    }

    var hookedCount = 0;
    for (var i = 0; i < exports.length; i++) {
        var exp = exports[i];
        if (exp.type !== "function") continue;

        var matched = false;
        for (var p = 0; p < patterns.length; p++) {
            if (exp.name.indexOf(patterns[p]) !== -1 &&
                (exp.name.indexOf("Send") !== -1 || exp.name.indexOf("Recv") !== -1 ||
                 exp.name.indexOf("Receive") !== -1 || exp.name.indexOf("Read") !== -1 ||
                 exp.name.indexOf("Write") !== -1)) {
                matched = true;
                break;
            }
        }

        if (!matched) continue;

        try {
            (function(exportName, address) {
                Interceptor.attach(address, {
                    onEnter: function (args) {
                        this.exportName = exportName;
                        // For AzNetworking methods, args layout is unknown.
                        // We log the call for discovery; actual data capture
                        // happens at the SSL layer.
                    },
                    onLeave: function (retval) {
                        log("[AzNet] " + this.exportName + " returned " + retval);
                    }
                });
                hookedCount++;
                hookStatus("AzNet:" + exportName, "success");
            })(exp.name, exp.address);
        } catch (e) {
            hookStatus("AzNet:" + exp.name, "error", e.toString());
        }
    }

    if (hookedCount === 0) {
        log("[*] No AzNetworking Send/Receive exports found (likely not exported or name-mangled)");
    } else {
        log("[+] Hooked " + hookedCount + " AzNetworking function(s)");
    }
}

// ---------------------------------------------------------------------------
//  Winsock hooks (supplementary -- to see connection targets)
// ---------------------------------------------------------------------------

function hookWinsock() {
    function getWs2Export(name) {
        var imp = findImportedFunction(name);
        if (imp !== null) return imp;
        try {
            return Module.getExportByName("ws2_32.dll", name);
        } catch (_) {
            return null;
        }
    }

    function formatSockaddr(sockaddr) {
        if (sockaddr.isNull()) return null;
        try {
            var family = sockaddr.readU16();
            if (family === 2) { // AF_INET
                var port = (sockaddr.add(2).readU8() << 8) | sockaddr.add(3).readU8();
                var ip = sockaddr.add(4).readU8() + "." +
                         sockaddr.add(5).readU8() + "." +
                         sockaddr.add(6).readU8() + "." +
                         sockaddr.add(7).readU8();
                return ip + ":" + port;
            }
        } catch (_) {}
        return null;
    }

    function formatFamily(family) {
        if (family === 2) return "AF_INET";
        if (family === 23) return "AF_INET6";
        return "AF_" + family;
    }

    function formatSockType(t) {
        if (t === 1) return "SOCK_STREAM";
        if (t === 2) return "SOCK_DGRAM";
        return "TYPE_" + t;
    }

    function decodeIoctl(code) {
        if (code === 0x9800000c) return "SIO_UDP_CONNRESET";
        if (code === 0xc8000006) return "SIO_GET_EXTENSION_FUNCTION_POINTER";
        if (code === 0x98000011) return "SIO_KEEPALIVE_VALS";
        if (code === 0xc8000019) return "SIO_LOOPBACK_FAST_PATH";
        if (code === 0x48000016) return "SIO_TCP_INFO";
        return "0x" + code.toString(16);
    }

    function formatGuidBytes(ptr16) {
        if (ptr16.isNull()) return null;
        try {
            var d1 = ptr16.readU32();
            var d2 = ptr16.add(4).readU16();
            var d3 = ptr16.add(6).readU16();
            var tail = [];
            for (var i = 0; i < 8; i++) {
                var b = ptr16.add(8 + i).readU8().toString(16);
                tail.push(b.length < 2 ? "0" + b : b);
            }
            return (
                ("00000000" + d1.toString(16)).slice(-8) + "-" +
                ("0000" + d2.toString(16)).slice(-4) + "-" +
                ("0000" + d3.toString(16)).slice(-4) + "-" +
                tail.slice(0, 2).join("") + "-" +
                tail.slice(2).join("")
            ).toLowerCase();
        } catch (_) {
            return null;
        }
    }

    function describeExtensionGuid(guid) {
        if (!guid) return "unknown";
        var known = {
            "25a207b9-ddf3-4660-8ee9-76e58c74063e": "ConnectEx",
            "7fda2e11-8630-436f-a031-f536a6eec157": "DisconnectEx",
            "b5367df1-cbac-11cf-95ca-00805f48a192": "AcceptEx",
            "b5367df2-cbac-11cf-95ca-00805f48a192": "GetAcceptExSockaddrs",
            "b5367df0-cbac-11cf-95ca-00805f48a192": "TransmitFile",
            "d9689da0-1f90-11d3-9971-00c04f68c876": "TransmitPackets",
            "f689d7c8-6f1f-436b-8a53-e54fe351c322": "WSARecvMsg",
            "a441e712-754f-43ca-84a7-0dee44cf606d": "WSASendMsg"
        };
        return known[guid] || guid;
    }

    function hookExtensionFunction(name, addr) {
        var hookName = "ext_" + name + "_" + ptrKey(addr);
        if (isHooked(hookName) || addr.isNull()) return;

        try {
            if (name === "WSASendMsg") {
                Interceptor.attach(addr, {
                    onEnter: function (args) {
                        this.sock = args[0];
                        this.target = null;
                        try {
                            var wsamsg = args[1];
                            this.target = formatSockaddr(wsamsg.readPointer());
                        } catch (_) {}
                    },
                    onLeave: function (retval) {
                        log("[ws2-ext] WSASendMsg(" + this.sock + ") -> " + (this.target || "unknown") + " ret=" + retval.toInt32());
                    }
                });
            } else if (name === "WSARecvMsg") {
                Interceptor.attach(addr, {
                    onEnter: function (args) {
                        this.sock = args[0];
                    },
                    onLeave: function (retval) {
                        log("[ws2-ext] WSARecvMsg(" + this.sock + ") ret=" + retval.toInt32());
                    }
                });
            } else if (name === "ConnectEx") {
                Interceptor.attach(addr, {
                    onEnter: function (args) {
                        this.sock = args[0];
                        this.target = formatSockaddr(args[1]);
                    },
                    onLeave: function (retval) {
                        log("[ws2-ext] ConnectEx(" + this.sock + ") -> " + (this.target || "unknown") + " ret=" + retval.toInt32());
                    }
                });
            } else if (name === "DisconnectEx") {
                Interceptor.attach(addr, {
                    onEnter: function (args) {
                        this.sock = args[0];
                    },
                    onLeave: function (retval) {
                        log("[ws2-ext] DisconnectEx(" + this.sock + ") ret=" + retval.toInt32());
                    }
                });
            } else if (name === "AcceptEx") {
                Interceptor.attach(addr, {
                    onEnter: function (args) {
                        this.listenSock = args[0];
                        this.acceptSock = args[1];
                    },
                    onLeave: function (retval) {
                        log("[ws2-ext] AcceptEx(" + this.listenSock + ", " + this.acceptSock + ") ret=" + retval.toInt32());
                    }
                });
            } else {
                Interceptor.attach(addr, {
                    onEnter: function (_) {
                        log("[ws2-ext] " + name + "()");
                    }
                });
            }

            hookStatus(hookName, "success");
            markHook(hookName);
            log("[ws2-ext] hooked " + name + " at " + addr);
        } catch (e) {
            hookStatus(hookName, "error", e.toString());
        }
    }

    try {
        var wsaSocketW = getWs2Export("WSASocketW");
        if (wsaSocketW && !isHooked("WSASocketW")) {
            Interceptor.attach(wsaSocketW, {
                onEnter: function (args) {
                    this.family = args[0].toInt32();
                    this.type = args[1].toInt32();
                    this.proto = args[2].toInt32();
                },
                onLeave: function (retval) {
                    log("[ws2] WSASocketW -> " + retval + " " +
                        formatFamily(this.family) + " " +
                        formatSockType(this.type) + " proto=" + this.proto);
                    if (this.type === 2 || this.proto === 17) {
                        rememberUdpSocket(retval, this.family, this.type, this.proto);
                    }
                }
            });
            hookStatus("WSASocketW", "success");
            markHook("WSASocketW");
        } else if (!wsaSocketW) {
            hookStatus("WSASocketW", "not_found");
        }

        var socketFn = getWs2Export("socket");
        if (socketFn && !isHooked("ws2_socket")) {
            Interceptor.attach(socketFn, {
                onEnter: function (args) {
                    this.family = args[0].toInt32();
                    this.type = args[1].toInt32();
                    this.proto = args[2].toInt32();
                },
                onLeave: function (retval) {
                    log("[ws2] socket -> " + retval + " " +
                        formatFamily(this.family) + " " +
                        formatSockType(this.type) + " proto=" + this.proto);
                    if (this.type === 2 || this.proto === 17) {
                        rememberUdpSocket(retval, this.family, this.type, this.proto);
                    }
                }
            });
            hookStatus("ws2_socket", "success");
            markHook("ws2_socket");
        } else if (!socketFn) {
            hookStatus("ws2_socket", "not_found");
        }

        var wsaConnect = getWs2Export("WSAConnect");
        if (wsaConnect && !isHooked("WSAConnect")) {
            Interceptor.attach(wsaConnect, {
                onEnter: function (args) {
                    var target = formatSockaddr(args[1]);
                    if (target) {
                        log("[ws2] WSAConnect() -> " + target);
                    }
                }
            });
            hookStatus("WSAConnect", "success");
            markHook("WSAConnect");
        } else if (!wsaConnect) {
            hookStatus("WSAConnect", "not_found");
        }

        var connect = getWs2Export("connect");
        if (connect && !isHooked("ws2_connect")) {
            Interceptor.attach(connect, {
                onEnter: function (args) {
                    var target = formatSockaddr(args[1]);
                    if (target) {
                        log("[ws2] connect() -> " + target);
                    }
                }
            });
            hookStatus("ws2_connect", "success");
            markHook("ws2_connect");
        } else if (!connect) {
            hookStatus("ws2_connect", "not_found");
        }

        var wsaSend = getWs2Export("WSASend");
        if (wsaSend && !isHooked("WSASend")) {
            Interceptor.attach(wsaSend, {
                onEnter: function (args) {
                    this.bufCount = args[2].toInt32();
                    log("[ws2] WSASend -> buffers=" + this.bufCount);
                }
            });
            hookStatus("WSASend", "success");
            markHook("WSASend");
        } else if (!wsaSend) {
            hookStatus("WSASend", "not_found");
        }

        var wsaRecv = getWs2Export("WSARecv");
        if (wsaRecv && !isHooked("WSARecv")) {
            Interceptor.attach(wsaRecv, {
                onEnter: function (args) {
                    this.bufCount = args[2].toInt32();
                    log("[ws2] WSARecv <- buffers=" + this.bufCount);
                }
            });
            hookStatus("WSARecv", "success");
            markHook("WSARecv");
        } else if (!wsaRecv) {
            hookStatus("WSARecv", "not_found");
        }

        var wsaRecvFrom = getWs2Export("WSARecvFrom");
        if (wsaRecvFrom && !isHooked("WSARecvFrom")) {
            Interceptor.attach(wsaRecvFrom, {
                onEnter: function (_) {
                    log("[ws2] WSARecvFrom <-");
                }
            });
            hookStatus("WSARecvFrom", "success");
            markHook("WSARecvFrom");
        } else if (!wsaRecvFrom) {
            hookStatus("WSARecvFrom", "not_found");
        }

        var wsaSendMsg = getWs2Export("WSASendMsg");
        if (wsaSendMsg && !isHooked("WSASendMsg")) {
            Interceptor.attach(wsaSendMsg, {
                onEnter: function (args) {
                    this.sock = args[0];
                    try {
                        var wsamsg = args[1];
                        this.target = formatSockaddr(wsamsg.readPointer());
                    } catch (_) {
                        this.target = null;
                    }
                },
                onLeave: function (retval) {
                    log("[ws2] WSASendMsg(" + this.sock + ") -> " + (this.target || "unknown") + " ret=" + retval.toInt32());
                }
            });
            hookStatus("WSASendMsg", "success");
            markHook("WSASendMsg");
        } else if (!wsaSendMsg) {
            hookStatus("WSASendMsg", "not_found");
        }

        var wsaSendTo = getWs2Export("WSASendTo");
        if (wsaSendTo && !isHooked("WSASendTo")) {
            Interceptor.attach(wsaSendTo, {
                onEnter: function (args) {
                    this.target = formatSockaddr(args[5]);
                    this.bufCount = args[2].toInt32();
                },
                onLeave: function (_) {
                    if (this.target) {
                        log("[ws2] WSASendTo -> " + this.target + " buffers=" + this.bufCount);
                    } else {
                        log("[ws2] WSASendTo -> buffers=" + this.bufCount);
                    }
                }
            });
            hookStatus("WSASendTo", "success");
            markHook("WSASendTo");
        } else if (!wsaSendTo) {
            hookStatus("WSASendTo", "not_found");
        }

        var sendto = getWs2Export("sendto");
        if (sendto && !isHooked("ws2_sendto")) {
            Interceptor.attach(sendto, {
                onEnter: function (args) {
                    this.target = formatSockaddr(args[4]);
                    this.len = args[2].toInt32();
                },
                onLeave: function (_) {
                    if (this.target) {
                        log("[ws2] sendto -> " + this.target + " (" + this.len + " bytes)");
                    }
                }
            });
            hookStatus("ws2_sendto", "success");
            markHook("ws2_sendto");
        } else if (!sendto) {
            hookStatus("ws2_sendto", "not_found");
        }

        var recvfrom = getWs2Export("recvfrom");
        if (recvfrom && !isHooked("ws2_recvfrom")) {
            Interceptor.attach(recvfrom, {
                onEnter: function (args) {
                    this.len = args[2].toInt32();
                },
                onLeave: function (retval) {
                    var moved = retval.toInt32();
                    if (moved > 0) {
                        log("[ws2] recvfrom <- " + moved + " bytes");
                    }
                }
            });
            hookStatus("ws2_recvfrom", "success");
            markHook("ws2_recvfrom");
        } else if (!recvfrom) {
            hookStatus("ws2_recvfrom", "not_found");
        }

        var send = getWs2Export("send");
        if (send && !isHooked("ws2_send")) {
            Interceptor.attach(send, {
                onEnter: function (args) {
                    this.len = args[2].toInt32();
                },
                onLeave: function (_) {
                    log("[ws2] send -> " + this.len + " bytes");
                }
            });
            hookStatus("ws2_send", "success");
            markHook("ws2_send");
        } else if (!send) {
            hookStatus("ws2_send", "not_found");
        }

        var recv = getWs2Export("recv");
        if (recv && !isHooked("ws2_recv")) {
            Interceptor.attach(recv, {
                onLeave: function (retval) {
                    var moved = retval.toInt32();
                    if (moved > 0) {
                        log("[ws2] recv <- " + moved + " bytes");
                    }
                }
            });
            hookStatus("ws2_recv", "success");
            markHook("ws2_recv");
        } else if (!recv) {
            hookStatus("ws2_recv", "not_found");
        }

        var getAddrInfoW = getWs2Export("GetAddrInfoW");
        if (getAddrInfoW && !isHooked("GetAddrInfoW")) {
            Interceptor.attach(getAddrInfoW, {
                onEnter: function (args) {
                    try {
                        var node = args[0].isNull() ? "" : args[0].readUtf16String();
                        var service = args[1].isNull() ? "" : args[1].readUtf16String();
                        log("[ws2] GetAddrInfoW -> node=" + node + " service=" + service);
                    } catch (_) {}
                }
            });
            hookStatus("GetAddrInfoW", "success");
            markHook("GetAddrInfoW");
        } else if (!getAddrInfoW) {
            hookStatus("GetAddrInfoW", "not_found");
        }

        var getaddrinfo = getWs2Export("getaddrinfo");
        if (getaddrinfo && !isHooked("getaddrinfo")) {
            Interceptor.attach(getaddrinfo, {
                onEnter: function (args) {
                    try {
                        var nodeA = args[0].isNull() ? "" : args[0].readUtf8String();
                        var serviceA = args[1].isNull() ? "" : args[1].readUtf8String();
                        log("[ws2] getaddrinfo -> node=" + nodeA + " service=" + serviceA);
                    } catch (_) {}
                }
            });
            hookStatus("getaddrinfo", "success");
            markHook("getaddrinfo");
        } else if (!getaddrinfo) {
            hookStatus("getaddrinfo", "not_found");
        }

        var bindFn = getWs2Export("bind");
        if (bindFn && !isHooked("ws2_bind")) {
            Interceptor.attach(bindFn, {
                onEnter: function (args) {
                    this.target = formatSockaddr(args[1]);
                    this.sock = args[0];
                },
                onLeave: function (retval) {
                    log("[ws2] bind(" + this.sock + ") -> " + (this.target || "unknown") + " ret=" + retval.toInt32());
                }
            });
            hookStatus("ws2_bind", "success");
            markHook("ws2_bind");
        } else if (!bindFn) {
            hookStatus("ws2_bind", "not_found");
        }

        var setsockoptFn = getWs2Export("setsockopt");
        if (setsockoptFn && !isHooked("ws2_setsockopt")) {
            Interceptor.attach(setsockoptFn, {
                onEnter: function (args) {
                    this.sock = args[0];
                    this.level = args[1].toInt32();
                    this.optname = args[2].toInt32();
                },
                onLeave: function (retval) {
                    log("[ws2] setsockopt(" + this.sock + ", level=" + this.level + ", opt=" + this.optname + ") ret=" + retval.toInt32());
                }
            });
            hookStatus("ws2_setsockopt", "success");
            markHook("ws2_setsockopt");
        } else if (!setsockoptFn) {
            hookStatus("ws2_setsockopt", "not_found");
        }

        var ioctlsocketFn = getWs2Export("ioctlsocket");
        if (ioctlsocketFn && !isHooked("ws2_ioctlsocket")) {
            Interceptor.attach(ioctlsocketFn, {
                onEnter: function (args) {
                    this.sock = args[0];
                    this.cmd = args[1].toUInt32();
                },
                onLeave: function (retval) {
                    log("[ws2] ioctlsocket(" + this.sock + ", cmd=0x" + this.cmd.toString(16) + ") ret=" + retval.toInt32());
                }
            });
            hookStatus("ws2_ioctlsocket", "success");
            markHook("ws2_ioctlsocket");
        } else if (!ioctlsocketFn) {
            hookStatus("ws2_ioctlsocket", "not_found");
        }

        var wsaIoctl = getWs2Export("WSAIoctl");
        if (wsaIoctl && !isHooked("WSAIoctl")) {
            Interceptor.attach(wsaIoctl, {
                onEnter: function (args) {
                    this.sock = args[0];
                    this.code = args[1].toUInt32();
                    this.inBuf = args[2];
                    this.inLen = args[3].toUInt32();
                    this.outBuf = args[4];
                    this.outLen = args[5].toUInt32();
                    this.bytesReturnedPtr = args[6];
                },
                onLeave: function (retval) {
                    var extra = "";
                    if (this.code === 0xc8000006 && !this.inBuf.isNull() && this.inLen >= 16) {
                        try {
                            var guid = formatGuidBytes(this.inBuf);
                            var guidName = describeExtensionGuid(guid);
                            extra = " guid=" + guidName;
                            if (retval.toInt32() === 0 && !this.outBuf.isNull() && this.outLen >= Process.pointerSize) {
                                var fnPtr = this.outBuf.readPointer();
                                extra += " fn=" + fnPtr;
                                hookExtensionFunction(guidName, fnPtr);
                            }
                        } catch (_) {}
                    }
                    log("[ws2] WSAIoctl(" + this.sock + ", " + decodeIoctl(this.code) + ")" + extra + " ret=" + retval.toInt32());
                }
            });
            hookStatus("WSAIoctl", "success");
            markHook("WSAIoctl");
        } else if (!wsaIoctl) {
            hookStatus("WSAIoctl", "not_found");
        }

        var wsaEventSelect = getWs2Export("WSAEventSelect");
        if (wsaEventSelect && !isHooked("WSAEventSelect")) {
            Interceptor.attach(wsaEventSelect, {
                onEnter: function (args) {
                    this.sock = args[0];
                    this.mask = args[2].toUInt32();
                },
                onLeave: function (retval) {
                    log("[ws2] WSAEventSelect(" + this.sock + ", mask=0x" + this.mask.toString(16) + ") ret=" + retval.toInt32());
                }
            });
            hookStatus("WSAEventSelect", "success");
            markHook("WSAEventSelect");
        } else if (!wsaEventSelect) {
            hookStatus("WSAEventSelect", "not_found");
        }

        var closesocket = getWs2Export("closesocket");
        if (closesocket && !isHooked("ws2_closesocket")) {
            Interceptor.attach(closesocket, {
                onEnter: function (args) {
                    log("[ws2] closesocket(" + args[0] + ")");
                }
            });
            hookStatus("ws2_closesocket", "success");
            markHook("ws2_closesocket");
        } else if (!closesocket) {
            hookStatus("ws2_closesocket", "not_found");
        }
    } catch (e) {
        hookStatus("winsock", "error", e.toString());
    }
}

function hookKernelSocketInfra() {
    function getApi(name) {
        var imp = findImportedFunction(name);
        if (imp !== null) return imp;
        try {
            return Module.getExportByName("kernel32.dll", name);
        } catch (_) {
            try {
                return Module.getExportByName("KernelBase.dll", name);
            } catch (_) {
                return null;
            }
        }
    }

    try {
        var createIocp = getApi("CreateIoCompletionPort");
        if (createIocp && !isHooked("CreateIoCompletionPort")) {
            Interceptor.attach(createIocp, {
                onEnter: function (args) {
                    this.fileHandle = args[0];
                    this.existingPort = args[1];
                    this.completionKey = args[2];
                    this.threads = args[3].toUInt32();
                },
                onLeave: function (retval) {
                    log("[iocp] CreateIoCompletionPort(file=" + this.fileHandle +
                        ", existing=" + this.existingPort +
                        ", key=" + this.completionKey +
                        ", threads=" + this.threads +
                        ") -> " + retval);
                }
            });
            hookStatus("CreateIoCompletionPort", "success");
            markHook("CreateIoCompletionPort");
        } else if (!createIocp) {
            hookStatus("CreateIoCompletionPort", "not_found");
        }

        var getQcs = getApi("GetQueuedCompletionStatus");
        if (getQcs && !isHooked("GetQueuedCompletionStatus")) {
            Interceptor.attach(getQcs, {
                onEnter: function (args) {
                    this.port = args[0];
                    this.bytesPtr = args[1];
                    this.keyPtr = args[2];
                    this.ovPtr = args[3];
                    this.timeout = args[4].toUInt32();
                },
                onLeave: function (retval) {
                    var ok = retval.toInt32();
                    var extra = "";
                    try {
                        var bytes = this.bytesPtr.isNull() ? 0 : this.bytesPtr.readU32();
                        var key = this.keyPtr.isNull() ? ptr("0") : this.keyPtr.readPointer();
                        var ov = this.ovPtr.isNull() ? ptr("0") : this.ovPtr.readPointer();
                        extra = " bytes=" + bytes + " key=" + key + " ov=" + ov;
                    } catch (_) {}
                    log("[iocp] GetQueuedCompletionStatus(port=" + this.port + ", timeout=" + this.timeout + ") -> " + ok + extra);
                }
            });
            hookStatus("GetQueuedCompletionStatus", "success");
            markHook("GetQueuedCompletionStatus");
        } else if (!getQcs) {
            hookStatus("GetQueuedCompletionStatus", "not_found");
        }

        var postQcs = getApi("PostQueuedCompletionStatus");
        if (postQcs && !isHooked("PostQueuedCompletionStatus")) {
            Interceptor.attach(postQcs, {
                onEnter: function (args) {
                    log("[iocp] PostQueuedCompletionStatus(port=" + args[0] +
                        ", bytes=" + args[1].toUInt32() +
                        ", key=" + args[2] +
                        ", ov=" + args[3] + ")");
                }
            });
            hookStatus("PostQueuedCompletionStatus", "success");
            markHook("PostQueuedCompletionStatus");
        } else if (!postQcs) {
            hookStatus("PostQueuedCompletionStatus", "not_found");
        }
    } catch (e) {
        hookStatus("kernel_socket_infra", "error", e.toString());
    }
}

function hookWinsockProviderSpi() {
    function getApi(name) {
        var modules = ["ws2_32.dll", "mswsock.dll", "wsock32.dll"];
        for (var i = 0; i < modules.length; i++) {
            try {
                var addr = Module.getExportByName(modules[i], name);
                if (addr) return addr;
            } catch (_) {}
        }
        return null;
    }

    function hookWspProc(name, addr, kind) {
        if (addr.isNull() || isWspPtrHooked(addr)) return;
        try {
            if (kind === "WSPSocket") {
                Interceptor.attach(addr, {
                    onEnter: function (args) {
                        this.family = args[0].toInt32();
                        this.type = args[1].toInt32();
                        this.proto = args[2].toInt32();
                    },
                    onLeave: function (retval) {
                        log("[wsp] WSPSocket -> " + retval + " " +
                            formatFamily(this.family) + " " +
                            formatSockType(this.type) + " proto=" + this.proto);
                        if (this.type === 2 || this.proto === 17) {
                            rememberUdpSocket(retval, this.family, this.type, this.proto);
                        }
                    }
                });
            } else if (kind === "WSPConnect") {
                Interceptor.attach(addr, {
                    onEnter: function (args) {
                        var target = formatSockaddr(args[1]);
                        if (target) {
                            log("[wsp] WSPConnect(" + args[0] + ") -> " + target);
                        }
                    }
                });
            } else if (kind === "WSPSendTo") {
                Interceptor.attach(addr, {
                    onEnter: function (args) {
                        var sock = args[0];
                        var target = formatSockaddr(args[4]);
                        if (isKnownUdpSocket(sock) || target) {
                            log("[wsp] WSPSendTo(" + sock + ") -> " + (target || "unknown"));
                        }
                    }
                });
            } else if (kind === "WSPIoctl") {
                Interceptor.attach(addr, {
                    onEnter: function (args) {
                        if (!isKnownUdpSocket(args[0])) return;
                        var code = args[3].toUInt32();
                        log("[wsp] WSPIoctl(" + args[0] + ", code=0x" + code.toString(16) + ")");
                    }
                });
            } else if (kind === "WSPCloseSocket") {
                Interceptor.attach(addr, {
                    onEnter: function (args) {
                        if (isKnownUdpSocket(args[0])) {
                            log("[wsp] WSPCloseSocket(" + args[0] + ")");
                        }
                    }
                });
            } else {
                Interceptor.attach(addr, {
                    onEnter: function (_) {
                        log("[wsp] " + name + "()");
                    }
                });
            }
            markWspPtr(addr);
            hookStatus("wsp_" + kind + "_" + ptrKey(addr), "success");
            log("[wsp] hooked " + kind + " at " + addr);
        } catch (e) {
            hookStatus("wsp_" + kind + "_" + ptrKey(addr), "error", e.toString());
        }
    }

    try {
        var wspStartup = getApi("WSPStartup");
        if (wspStartup && !isHooked("WSPStartup")) {
            Interceptor.attach(wspStartup, {
                onEnter: function (args) {
                    this.procTable = args[4];
                },
                onLeave: function (retval) {
                    var ok = retval.toInt32() === 0;
                    log("[wsp] WSPStartup -> " + retval.toInt32());
                    if (!ok || this.procTable.isNull()) return;

                    try {
                        var table = this.procTable;
                        hookWspProc("WSPCloseSocket", table.add(6 * Process.pointerSize).readPointer(), "WSPCloseSocket");
                        hookWspProc("WSPConnect", table.add(7 * Process.pointerSize).readPointer(), "WSPConnect");
                        hookWspProc("WSPIoctl", table.add(16 * Process.pointerSize).readPointer(), "WSPIoctl");
                        hookWspProc("WSPSendTo", table.add(24 * Process.pointerSize).readPointer(), "WSPSendTo");
                        hookWspProc("WSPSocket", table.add(28 * Process.pointerSize).readPointer(), "WSPSocket");
                    } catch (e) {
                        hookStatus("WSPStartup_table_parse", "error", e.toString());
                    }
                }
            });
            hookStatus("WSPStartup", "success");
            markHook("WSPStartup");
        } else if (!wspStartup) {
            hookStatus("WSPStartup", "not_found");
        }
    } catch (e) {
        hookStatus("winsock_provider_spi", "error", e.toString());
    }
}

function hookInternalRepFunctions() {
    try {
        var base = getMainModule().base;

        var transportCtor = base.add(INTERNAL_RVA_TRANSPORT_CTOR);
        if (!isHooked("internal_rep_transport_ctor")) {
            Interceptor.attach(transportCtor, {
                onEnter: function (args) {
                    this.thisPtr = args[0];
                    hookTransportObjectVirtuals(this.thisPtr);
                    log("[rep-int] transport ctor enter this=" + this.thisPtr +
                        " arg1=" + args[1] + " arg2=" + args[2] + " arg3=" + args[3] +
                        " state=" + describeTransportState(this.thisPtr));
                    if (!internalRepBacktraceLogged.transportCtor) {
                        internalRepBacktraceLogged.transportCtor = true;
                        try {
                            var frames = Thread.backtrace(this.context, Backtracer.ACCURATE)
                                .slice(0, 12);
                            var formatted = formatBacktrace(frames);
                            log("[rep-int] transport ctor bt " + formatted);
                        } catch (_) {}
                    }
                },
                onLeave: function (retval) {
                    hookTransportObjectVirtuals(this.thisPtr);
                    log("[rep-int] transport ctor leave ret=" + retval +
                        " state=" + describeTransportState(this.thisPtr));
                }
            });
            hookStatus("internal_rep_transport_ctor", "success");
            markHook("internal_rep_transport_ctor");
        }

        var secureInit = base.add(INTERNAL_RVA_SECURE_INIT);
        if (!isHooked("internal_rep_secure_init")) {
            Interceptor.attach(secureInit, {
                onEnter: function (args) {
                    this.ctx = args[0];
                    var verifyFlag = "<?>", modeFlag = "<?>";
                    try {
                        verifyFlag = this.ctx.add(0x288).readPointer();
                    } catch (_) {}
                    try {
                        modeFlag = this.ctx.add(0x270).readU8();
                    } catch (_) {}
                    log("[rep-int] secure init enter ctx=" + this.ctx +
                        " verifyField=" + verifyFlag +
                        " modeField=" + modeFlag);
                    if (!internalRepBacktraceLogged.secureInit) {
                        internalRepBacktraceLogged.secureInit = true;
                        try {
                            var frames = Thread.backtrace(this.context, Backtracer.ACCURATE)
                                .slice(0, 12);
                            var formatted = formatBacktrace(frames);
                            log("[rep-int] secure init bt " + formatted);
                        } catch (_) {}
                    }
                },
                onLeave: function (retval) {
                    log("[rep-int] secure init leave ret=" + retval);
                }
            });
            hookStatus("internal_rep_secure_init", "success");
            markHook("internal_rep_secure_init");
        }

        var repStartHelper = base.add(INTERNAL_RVA_REP_START_HELPER);
        if (!isHooked("internal_rep_start_helper")) {
            Interceptor.attach(repStartHelper, {
                onEnter: function (args) {
                    this.gameConn = args[0];
                    this.arg1 = args[1];
                    this.repObj = ptr("0");
                    try {
                        this.repObj = this.gameConn.add(0x1000).readPointer();
                    } catch (_) {}
                    log("[rep-int] start helper enter gameConn=" + this.gameConn +
                        " arg1=" + this.arg1 + " repObj=" + this.repObj);
                    hookRepObjectVirtuals(this.repObj);
                    if (!internalRepBacktraceLogged.repStartHelper) {
                        internalRepBacktraceLogged.repStartHelper = true;
                        try {
                            var helperFrames = Thread.backtrace(this.context, Backtracer.ACCURATE)
                                .slice(0, 12);
                            log("[rep-int] start helper bt " + formatBacktrace(helperFrames));
                        } catch (_) {}
                    }
                },
                onLeave: function (retval) {
                    log("[rep-int] start helper leave ret=" + retval);
                }
            });
            hookStatus("internal_rep_start_helper", "success");
            markHook("internal_rep_start_helper");
        }

        var gameConnState = base.add(INTERNAL_RVA_GAMECONN_STATE);
        if (!isHooked("internal_gameconn_state")) {
            Interceptor.attach(gameConnState, {
                onEnter: function (args) {
                    this.gameConn = args[0];
                    this.arg1 = args[1];
                    this.repObj = ptr("0");
                    try {
                        this.repObj = this.gameConn.add(0x1000).readPointer();
                    } catch (_) {}
                    if (!this.repObj.isNull()) {
                        if (gameConnStateLogCount < 20) {
                            gameConnStateLogCount++;
                            log("[rep-sm] tick gameConn=" + this.gameConn +
                                " arg1=" + this.arg1 + " repObj=" + this.repObj +
                                " count=" + gameConnStateLogCount);
                        }
                        hookRepObjectVirtuals(this.repObj);
                    }
                    if (!internalRepBacktraceLogged.gameConnState && !this.repObj.isNull()) {
                        internalRepBacktraceLogged.gameConnState = true;
                        try {
                            var tickFrames = Thread.backtrace(this.context, Backtracer.ACCURATE)
                                .slice(0, 12);
                            log("[rep-sm] tick bt " + formatBacktrace(tickFrames));
                        } catch (_) {}
                    }
                },
                onLeave: function (retval) {
                    if (!this.repObj.isNull() && gameConnStateLogCount <= 20) {
                        log("[rep-sm] tick leave ret=" + retval + " repObj=" + this.repObj);
                    }
                }
            });
            hookStatus("internal_gameconn_state", "success");
            markHook("internal_gameconn_state");
        }

        var repReadySetter = base.add(INTERNAL_RVA_REP_READY_SETTER);
        if (!isHooked("internal_rep_ready_setter")) {
            Interceptor.attach(repReadySetter, {
                onEnter: function (args) {
                    this.repObj = args[0];
                    this.arg2 = args[1];
                    var readyBefore = "<?>";
                    try {
                        readyBefore = this.repObj.add(0x601).readU8();
                    } catch (_) {}
                    log("[rep-ready] setter enter repObj=" + this.repObj +
                        " arg2=" + this.arg2 + " readyBefore=" + readyBefore);
                    if (!internalRepBacktraceLogged.repReadySetter) {
                        internalRepBacktraceLogged.repReadySetter = true;
                        try {
                            var setterFrames = Thread.backtrace(this.context, Backtracer.ACCURATE)
                                .slice(0, 12);
                            log("[rep-ready] setter bt " + formatBacktrace(setterFrames));
                        } catch (_) {}
                    }
                },
                onLeave: function (retval) {
                    var readyAfter = "<?>";
                    try {
                        readyAfter = this.repObj.add(0x601).readU8();
                    } catch (_) {}
                    log("[rep-ready] setter leave ret=" + retval +
                        " readyAfter=" + readyAfter + " repObj=" + this.repObj);
                }
            });
            hookStatus("internal_rep_ready_setter", "success");
            markHook("internal_rep_ready_setter");
        }

        var repReadyReset = base.add(INTERNAL_RVA_REP_READY_RESET);
        if (!isHooked("internal_rep_ready_reset")) {
            Interceptor.attach(repReadyReset, {
                onEnter: function (args) {
                    this.repObj = args[0];
                    var readyBefore = "<?>";
                    try {
                        readyBefore = this.repObj.add(0x601).readU8();
                    } catch (_) {}
                    log("[rep-ready] reset enter repObj=" + this.repObj +
                        " readyBefore=" + readyBefore);
                    if (!internalRepBacktraceLogged.repReadyReset) {
                        internalRepBacktraceLogged.repReadyReset = true;
                        try {
                            var resetFrames = Thread.backtrace(this.context, Backtracer.ACCURATE)
                                .slice(0, 12);
                            log("[rep-ready] reset bt " + formatBacktrace(resetFrames));
                        } catch (_) {}
                    }
                },
                onLeave: function (retval) {
                    var readyAfter = "<?>";
                    try {
                        readyAfter = this.repObj.add(0x601).readU8();
                    } catch (_) {}
                    log("[rep-ready] reset leave ret=" + retval +
                        " readyAfter=" + readyAfter + " repObj=" + this.repObj);
                }
            });
            hookStatus("internal_rep_ready_reset", "success");
            markHook("internal_rep_ready_reset");
        }
    } catch (e) {
        hookStatus("internal_rep_functions", "error", e.toString());
    }
}

function hookNtdllSocketInfra() {
    function getApi(name) {
        try {
            return Module.getExportByName("ntdll.dll", name);
        } catch (_) {
            return null;
        }
    }

    try {
        var ntDeviceIoControlFile = getApi("NtDeviceIoControlFile");
        if (ntDeviceIoControlFile && !isHooked("NtDeviceIoControlFile")) {
            Interceptor.attach(ntDeviceIoControlFile, {
                onEnter: function (args) {
                    this.fileHandle = args[0];
                    this.ioctl = args[5].toUInt32();
                    this.shouldLog = isKnownUdpSocket(this.fileHandle);
                },
                onLeave: function (retval) {
                    if (!this.shouldLog) return;
                    log("[ntdll] NtDeviceIoControlFile(handle=" + this.fileHandle +
                        ", ioctl=0x" + this.ioctl.toString(16) +
                        ") -> 0x" + retval.toUInt32().toString(16));
                }
            });
            hookStatus("NtDeviceIoControlFile", "success");
            markHook("NtDeviceIoControlFile");
        } else if (!ntDeviceIoControlFile) {
            hookStatus("NtDeviceIoControlFile", "not_found");
        }

        var ntClose = getApi("NtClose");
        if (ntClose && !isHooked("NtClose")) {
            Interceptor.attach(ntClose, {
                onEnter: function (args) {
                    if (isKnownUdpSocket(args[0])) {
                        log("[ntdll] NtClose(handle=" + args[0] + ")");
                    }
                }
            });
            hookStatus("NtClose", "success");
            markHook("NtClose");
        } else if (!ntClose) {
            hookStatus("NtClose", "not_found");
        }
    } catch (e) {
        hookStatus("ntdll_socket_infra", "error", e.toString());
    }
}

// ---------------------------------------------------------------------------
//  WinHTTP / WinINet hooks (supplementary -- to see plain HTTP reachability)
// ---------------------------------------------------------------------------

function hookWinHttp() {
    function getWinHttpExport(name) {
        var imp = findImportedFunction(name);
        if (imp !== null) return imp;
        try {
            return Module.getExportByName("winhttp.dll", name);
        } catch (_) {
            return null;
        }
    }

    function readWide(ptr) {
        if (ptr.isNull()) return "";
        try {
            return ptr.readUtf16String();
        } catch (_) {
            return "";
        }
    }

    function readAscii(ptr, len) {
        if (ptr.isNull()) return "";
        try {
            if (len !== undefined && len !== null && len > 0) {
                return ptr.readAnsiString(len);
            }
            return ptr.readAnsiString();
        } catch (_) {
            return "";
        }
    }

    function boolResult(retval) {
        return !retval.isNull() && retval.toInt32() !== 0;
    }

    function decodeWinHttpFlags(flags) {
        var known = [
            [0x00000001, "RESOLVING_NAME"],
            [0x00000002, "NAME_RESOLVED"],
            [0x00000004, "CONNECTING"],
            [0x00000008, "CONNECTED"],
            [0x00000010, "SENDING_REQUEST"],
            [0x00000020, "REQUEST_SENT"],
            [0x00000040, "RECEIVING_RESPONSE"],
            [0x00000080, "RESPONSE_RECEIVED"],
            [0x00000100, "CLOSING_CONNECTION"],
            [0x00000200, "CONNECTION_CLOSED"],
            [0x00000400, "HANDLE_CREATED"],
            [0x00000800, "HANDLE_CLOSING"],
            [0x00001000, "DETECTING_PROXY"],
            [0x00002000, "REDIRECT"],
            [0x00004000, "INTERMEDIATE_RESPONSE"],
            [0x00008000, "SECURE_FAILURE"],
            [0x00010000, "HEADERS_AVAILABLE"],
            [0x00020000, "DATA_AVAILABLE"],
            [0x00040000, "READ_COMPLETE"],
            [0x00080000, "WRITE_COMPLETE"],
            [0x00100000, "REQUEST_ERROR"],
            [0x00200000, "SENDREQUEST_COMPLETE"],
            [0x00400000, "GETPROXYFORURL_COMPLETE"],
            [0x00800000, "CLOSE_COMPLETE"],
            [0x20000000, "HANDLES"],
            [0x3FFFFFFF, "ALL_COMPLETIONS"]
        ];
        var parts = [];
        for (var i = 0; i < known.length; i++) {
            if ((flags & known[i][0]) === known[i][0]) {
                parts.push(known[i][1]);
            }
        }
        return parts.join("|") || ("0x" + flags.toString(16));
    }

    function describeRequestHandle(hRequest) {
        var info = winHttpRequestMap[ptrKey(hRequest)];
        if (!info) return "handle=" + hRequest;
        return info.verb + " https://" + info.host + ":" + info.port + info.objectName;
    }

    try {
        var setStatusCallback = getWinHttpExport("WinHttpSetStatusCallback");
        if (setStatusCallback && !isHooked("WinHttpSetStatusCallback")) {
            Interceptor.attach(setStatusCallback, {
                onEnter: function (args) {
                    var cb = args[1];
                    var flags = args[2].toUInt32();
                    log("[winhttp] set status callback cb=" + cb + " flags=" + decodeWinHttpFlags(flags));
                    if (!cb.isNull()) {
                        try {
                            Interceptor.attach(cb, {
                                onEnter: function (cbArgs) {
                                    var status = cbArgs[2].toUInt32();
                                    var infoLen = cbArgs[4].toUInt32();
                                    log("[winhttp-cb] status=" + decodeWinHttpFlags(status) + " len=" + infoLen);
                                }
                            });
                        } catch (_) {}
                    }
                }
            });
            hookStatus("WinHttpSetStatusCallback", "success");
            markHook("WinHttpSetStatusCallback");
        } else if (!setStatusCallback) {
            hookStatus("WinHttpSetStatusCallback", "not_found");
        }

        var connect = getWinHttpExport("WinHttpConnect");
        if (connect && !isHooked("WinHttpConnect")) {
            Interceptor.attach(connect, {
                onEnter: function (args) {
                    this.host = readWide(args[1]);
                    this.port = args[2].toInt32();
                    log("[winhttp] connect -> " + this.host + ":" + this.port);
                },
                onLeave: function (retval) {
                    if (!retval.isNull()) {
                        winHttpConnectMap[ptrKey(retval)] = {
                            host: this.host,
                            port: this.port
                        };
                    }
                }
            });
            hookStatus("WinHttpConnect", "success");
            markHook("WinHttpConnect");
        } else if (!connect) {
            hookStatus("WinHttpConnect", "not_found");
        }

        var openRequest = getWinHttpExport("WinHttpOpenRequest");
        if (openRequest && !isHooked("WinHttpOpenRequest")) {
            Interceptor.attach(openRequest, {
                onEnter: function (args) {
                    this.connectHandle = args[0];
                    this.verb = readWide(args[1]);
                    this.objectName = readWide(args[2]);
                    var conn = winHttpConnectMap[ptrKey(this.connectHandle)];
                    if (conn) {
                        log("[winhttp] request -> " + this.verb + " https://" + conn.host + ":" + conn.port + this.objectName);
                    } else {
                        log("[winhttp] request -> " + this.verb + " " + this.objectName);
                    }
                },
                onLeave: function (retval) {
                    if (!retval.isNull()) {
                        var conn = winHttpConnectMap[ptrKey(this.connectHandle)] || { host: "?", port: 0 };
                        winHttpRequestMap[ptrKey(retval)] = {
                            host: conn.host,
                            port: conn.port,
                            verb: this.verb,
                            objectName: this.objectName
                        };
                    }
                }
            });
            hookStatus("WinHttpOpenRequest", "success");
            markHook("WinHttpOpenRequest");
        } else if (!openRequest) {
            hookStatus("WinHttpOpenRequest", "not_found");
        }

        var sendRequest = getWinHttpExport("WinHttpSendRequest");
        if (sendRequest && !isHooked("WinHttpSendRequest")) {
            Interceptor.attach(sendRequest, {
                onEnter: function (args) {
                    this.requestHandle = args[0];
                    log("[winhttp] send request -> " + describeRequestHandle(this.requestHandle));
                },
                onLeave: function (retval) {
                    if (!boolResult(retval) && _GetLastError !== null) {
                        log("[winhttp] send request failed gle=" + _GetLastError() + " -> " + describeRequestHandle(this.requestHandle));
                    }
                }
            });
            hookStatus("WinHttpSendRequest", "success");
            markHook("WinHttpSendRequest");
        } else if (!sendRequest) {
            hookStatus("WinHttpSendRequest", "not_found");
        }

        var receiveResponse = getWinHttpExport("WinHttpReceiveResponse");
        if (receiveResponse && !isHooked("WinHttpReceiveResponse")) {
            Interceptor.attach(receiveResponse, {
                onEnter: function (args) {
                    this.requestHandle = args[0];
                },
                onLeave: function (retval) {
                    if (boolResult(retval)) {
                        log("[winhttp] receive response -> success -> " + describeRequestHandle(this.requestHandle));
                    } else if (_GetLastError !== null) {
                        log("[winhttp] receive response failed gle=" + _GetLastError() + " -> " + describeRequestHandle(this.requestHandle));
                    }
                }
            });
            hookStatus("WinHttpReceiveResponse", "success");
            markHook("WinHttpReceiveResponse");
        } else if (!receiveResponse) {
            hookStatus("WinHttpReceiveResponse", "not_found");
        }

        var queryHeaders = getWinHttpExport("WinHttpQueryHeaders");
        if (queryHeaders && !isHooked("WinHttpQueryHeaders")) {
            Interceptor.attach(queryHeaders, {
                onEnter: function (args) {
                    this.requestHandle = args[0];
                    this.infoLevel = args[1].toUInt32();
                    this.buffer = args[3];
                    this.bufferLenPtr = args[4];
                },
                onLeave: function (retval) {
                    if (!boolResult(retval)) {
                        return;
                    }
                    var level = this.infoLevel & 0xffff;
                    try {
                        if (level === 19 && !this.buffer.isNull()) { // WINHTTP_QUERY_STATUS_CODE
                            log("[winhttp] status code -> " + readWide(this.buffer) + " -> " + describeRequestHandle(this.requestHandle));
                        } else if (level === 22 && !this.buffer.isNull()) { // WINHTTP_QUERY_CONTENT_LENGTH
                            log("[winhttp] content-length -> " + readWide(this.buffer) + " -> " + describeRequestHandle(this.requestHandle));
                        } else if (level === 5 && !this.buffer.isNull()) { // WINHTTP_QUERY_RAW_HEADERS_CRLF
                            var chars = 0;
                            if (!this.bufferLenPtr.isNull()) {
                                chars = this.bufferLenPtr.readU32() / 2;
                            }
                            var hdrs = readWide(this.buffer);
                            if (hdrs && hdrs.length > 0) {
                                log("[winhttp] raw headers -> " + describeRequestHandle(this.requestHandle) + " :: " + hdrs.replace(/\r\n/g, " | "));
                            }
                        }
                    } catch (_) {}
                }
            });
            hookStatus("WinHttpQueryHeaders", "success");
            markHook("WinHttpQueryHeaders");
        } else if (!queryHeaders) {
            hookStatus("WinHttpQueryHeaders", "not_found");
        }

        var readData = getWinHttpExport("WinHttpReadData");
        if (readData && !isHooked("WinHttpReadData")) {
            Interceptor.attach(readData, {
                onEnter: function (args) {
                    this.requestHandle = args[0];
                    this.bytesReadPtr = args[3];
                },
                onLeave: function (retval) {
                    if (boolResult(retval) && !this.bytesReadPtr.isNull()) {
                        try {
                            log("[winhttp] read data -> " + this.bytesReadPtr.readU32() + " bytes -> " + describeRequestHandle(this.requestHandle));
                        } catch (_) {}
                    } else if (!boolResult(retval) && _GetLastError !== null) {
                        log("[winhttp] read data failed gle=" + _GetLastError() + " -> " + describeRequestHandle(this.requestHandle));
                    }
                }
            });
            hookStatus("WinHttpReadData", "success");
            markHook("WinHttpReadData");
        } else if (!readData) {
            hookStatus("WinHttpReadData", "not_found");
        }
    } catch (e) {
        hookStatus("winhttp", "error", e.toString());
    }
}

function hookWinInet() {
    function getWinInetExport(name) {
        var imp = findImportedFunction(name);
        if (imp !== null) return imp;
        try {
            return Module.getExportByName("wininet.dll", name);
        } catch (_) {
            return null;
        }
    }

    function readWide(ptr) {
        if (ptr.isNull()) return "";
        try {
            return ptr.readUtf16String();
        } catch (_) {
            return "";
        }
    }

    try {
        var internetConnect = getWinInetExport("InternetConnectW");
        if (internetConnect && !isHooked("InternetConnectW")) {
            Interceptor.attach(internetConnect, {
                onEnter: function (args) {
                    var server = readWide(args[1]);
                    var port = args[3].toInt32();
                    log("[wininet] connect -> " + server + ":" + port);
                }
            });
            hookStatus("InternetConnectW", "success");
            markHook("InternetConnectW");
        } else if (!internetConnect) {
            hookStatus("InternetConnectW", "not_found");
        }

        var httpOpenRequest = getWinInetExport("HttpOpenRequestW");
        if (httpOpenRequest && !isHooked("HttpOpenRequestW")) {
            Interceptor.attach(httpOpenRequest, {
                onEnter: function (args) {
                    var verb = readWide(args[1]);
                    var objectName = readWide(args[2]);
                    log("[wininet] request -> " + verb + " " + objectName);
                }
            });
            hookStatus("HttpOpenRequestW", "success");
            markHook("HttpOpenRequestW");
        } else if (!httpOpenRequest) {
            hookStatus("HttpOpenRequestW", "not_found");
        }
    } catch (e) {
        hookStatus("wininet", "error", e.toString());
    }
}

function hookSteamApi() {
    function getSteamExport(name) {
        var imp = findImportedFunction(name);
        if (imp !== null) return imp;
        try {
            return Module.getExportByName("steam_api64.dll", name);
        } catch (_) {
            return null;
        }
    }

    try {
        var steamInit = getSteamExport("SteamAPI_Init");
        if (steamInit && !isHooked("SteamAPI_Init")) {
            Interceptor.attach(steamInit, {
                onLeave: function (retval) {
                    log("[steam] SteamAPI_Init -> " + retval.toInt32());
                }
            });
            hookStatus("SteamAPI_Init", "success");
            markHook("SteamAPI_Init");
        } else if (!steamInit) {
            hookStatus("SteamAPI_Init", "not_found");
        }

        var steamContext = getSteamExport("SteamInternal_ContextInit");
        if (steamContext && !isHooked("SteamInternal_ContextInit")) {
            Interceptor.attach(steamContext, {
                onEnter: function (_) {
                    log("[steam] SteamInternal_ContextInit");
                }
            });
            hookStatus("SteamInternal_ContextInit", "success");
            markHook("SteamInternal_ContextInit");
        } else if (!steamContext) {
            hookStatus("SteamInternal_ContextInit", "not_found");
        }
    } catch (e) {
        hookStatus("steam_api", "error", e.toString());
    }
}

function hookProcessLifecycle() {
    function getApi(name, modules) {
        var imp = findImportedFunction(name);
        if (imp !== null) return imp;
        for (var i = 0; i < modules.length; i++) {
            try {
                var addr = Module.getExportByName(modules[i], name);
                if (addr) return addr;
            } catch (_) {}
        }
        return null;
    }

    try {
        var exitProcess = getApi("ExitProcess", ["kernel32.dll", "KernelBase.dll"]);
        if (exitProcess && !isHooked("ExitProcess")) {
            Interceptor.attach(exitProcess, {
                onEnter: function (args) {
                    log("[proc] ExitProcess(" + args[0].toInt32() + ")");
                }
            });
            hookStatus("ExitProcess", "success");
            markHook("ExitProcess");
        } else if (!exitProcess) {
            hookStatus("ExitProcess", "not_found");
        }

        var terminateProcess = getApi("TerminateProcess", ["kernel32.dll", "KernelBase.dll"]);
        if (terminateProcess && !isHooked("TerminateProcess")) {
            Interceptor.attach(terminateProcess, {
                onEnter: function (args) {
                    log("[proc] TerminateProcess(handle=" + args[0] + ", code=" + args[1].toInt32() + ")");
                }
            });
            hookStatus("TerminateProcess", "success");
            markHook("TerminateProcess");
        } else if (!terminateProcess) {
            hookStatus("TerminateProcess", "not_found");
        }

        var rtlExit = getApi("RtlExitUserProcess", ["ntdll.dll"]);
        if (rtlExit && !isHooked("RtlExitUserProcess")) {
            Interceptor.attach(rtlExit, {
                onEnter: function (args) {
                    log("[proc] RtlExitUserProcess(" + args[0].toInt32() + ")");
                }
            });
            hookStatus("RtlExitUserProcess", "success");
            markHook("RtlExitUserProcess");
        } else if (!rtlExit) {
            hookStatus("RtlExitUserProcess", "not_found");
        }

        var raiseFailFast = getApi("RaiseFailFastException", ["kernel32.dll", "KernelBase.dll"]);
        if (raiseFailFast && !isHooked("RaiseFailFastException")) {
            Interceptor.attach(raiseFailFast, {
                onEnter: function (_) {
                    log("[proc] RaiseFailFastException");
                }
            });
            hookStatus("RaiseFailFastException", "success");
            markHook("RaiseFailFastException");
        } else if (!raiseFailFast) {
            hookStatus("RaiseFailFastException", "not_found");
        }

        var abortFn = getApi("abort", ["ucrtbase.dll", "msvcrt.dll"]);
        if (abortFn && !isHooked("abort")) {
            Interceptor.attach(abortFn, {
                onEnter: function (_) {
                    log("[proc] abort()");
                }
            });
            hookStatus("abort", "success");
            markHook("abort");
        } else if (!abortFn) {
            hookStatus("abort", "not_found");
        }
    } catch (e) {
        hookStatus("process_lifecycle", "error", e.toString());
    }
}

function hookUser32Startup() {
    function getApi(name) {
        var imp = findImportedFunction(name);
        if (imp !== null) return imp;
        try {
            return Module.getExportByName("user32.dll", name);
        } catch (_) {
            return null;
        }
    }

    function readMaybeWide(ptr) {
        if (ptr.isNull()) return "";
        try {
            return ptr.readUtf16String();
        } catch (_) {
            try {
                return ptr.readUtf8String();
            } catch (_) {
                return "";
            }
        }
    }

    try {
        var createWindowExW = getApi("CreateWindowExW");
        if (createWindowExW && !isHooked("CreateWindowExW")) {
            Interceptor.attach(createWindowExW, {
                onEnter: function (args) {
                    var cls = readMaybeWide(args[1]);
                    var title = readMaybeWide(args[2]);
                    log("[ui] CreateWindowExW class=" + cls + " title=" + title);
                }
            });
            hookStatus("CreateWindowExW", "success");
            markHook("CreateWindowExW");
        } else if (!createWindowExW) {
            hookStatus("CreateWindowExW", "not_found");
        }

        var createWindowExA = getApi("CreateWindowExA");
        if (createWindowExA && !isHooked("CreateWindowExA")) {
            Interceptor.attach(createWindowExA, {
                onEnter: function (args) {
                    var cls = readMaybeWide(args[1]);
                    var title = readMaybeWide(args[2]);
                    log("[ui] CreateWindowExA class=" + cls + " title=" + title);
                }
            });
            hookStatus("CreateWindowExA", "success");
            markHook("CreateWindowExA");
        } else if (!createWindowExA) {
            hookStatus("CreateWindowExA", "not_found");
        }

        var showWindow = getApi("ShowWindow");
        if (showWindow && !isHooked("ShowWindow")) {
            Interceptor.attach(showWindow, {
                onEnter: function (args) {
                    log("[ui] ShowWindow cmd=" + args[1].toInt32());
                }
            });
            hookStatus("ShowWindow", "success");
            markHook("ShowWindow");
        } else if (!showWindow) {
            hookStatus("ShowWindow", "not_found");
        }

        var messageBoxW = getApi("MessageBoxW");
        if (messageBoxW && !isHooked("MessageBoxW")) {
            Interceptor.attach(messageBoxW, {
                onEnter: function (args) {
                    var text = readMaybeWide(args[1]);
                    var caption = readMaybeWide(args[2]);
                    log("[ui] MessageBoxW caption=" + caption + " text=" + text);
                }
            });
            hookStatus("MessageBoxW", "success");
            markHook("MessageBoxW");
        } else if (!messageBoxW) {
            hookStatus("MessageBoxW", "not_found");
        }
    } catch (e) {
        hookStatus("user32_startup", "error", e.toString());
    }
}

function hookModuleLoads() {
    function tryExport(moduleName, exportName) {
        try {
            return Module.getExportByName(moduleName, exportName);
        } catch (_) {
            return null;
        }
    }

    function attachLoadHook(exportName, wide) {
        var addr = tryExport("kernel32.dll", exportName) || tryExport("KernelBase.dll", exportName);
        if (!addr || isHooked(exportName)) return;
        Interceptor.attach(addr, {
            onEnter: function (args) {
                this.path = "";
                try {
                    this.path = wide ? args[0].readUtf16String() : args[0].readUtf8String();
                } catch (_) {}
            },
            onLeave: function (retval) {
                if (!retval.isNull() && this.path) {
                    log("[loader] " + exportName + " -> " + this.path);
                    retryDeferredHooks();
                }
            }
        });
        hookStatus(exportName, "success");
        markHook(exportName);
    }

    try {
        attachLoadHook("LoadLibraryW", true);
        attachLoadHook("LoadLibraryA", false);
        attachLoadHook("LoadLibraryExW", true);
        attachLoadHook("LoadLibraryExA", false);
    } catch (e) {
        hookStatus("loader_hooks", "error", e.toString());
    }
}

function retryDeferredHooks() {
    hookWinsock();
    hookWinHttp();
    hookWinInet();
    hookSteamApi();
    hookProcessLifecycle();
    hookUser32Startup();
}

function scheduleDeferredHookRetries(seconds) {
    retryDeadline = Date.now() + (seconds * 1000);
    if (pendingRetryTimer !== null) {
        return;
    }
    pendingRetryTimer = setInterval(function () {
        retryDeferredHooks();
        if (Date.now() >= retryDeadline) {
            clearInterval(pendingRetryTimer);
            pendingRetryTimer = null;
            log("[*] Deferred network hook retries finished");
        }
    }, 1000);
}

// ---------------------------------------------------------------------------
//  Main hook installation
// ---------------------------------------------------------------------------

function installHooks() {
    log("=== Frida DTLS/TLS Hook for New World ===");
    log("[*] PID: " + Process.id);
    log("[*] Main module: " + getMainModule().name + " @ " + getMainModule().base);
    log("[*] Architecture: " + Process.arch);

    // Install the cheap, early hooks first so short-lived startup failures still
    // give us some network signal before the heavier SSL scans run.
    hookWinsock();
    hookWinsockProviderSpi();
    hookKernelSocketInfra();
    hookNtdllSocketInfra();
    hookInternalRepFunctions();
    hookWinHttp();
    hookWinInet();
    hookSteamApi();
    hookProcessLifecycle();
    hookUser32Startup();
    hookModuleLoads();
    scheduleDeferredHookRetries(30);

    // AzNetworking layer next; still cheap if symbols exist.
    hookAzNetworking();

    log("[*] Searching for SSL functions...");

    // The list of OpenSSL / BoringSSL functions we want to hook
    var targets = [
        { name: "SSL_read",      dir: "read",  ex: false },
        { name: "SSL_write",     dir: "write", ex: false },
        { name: "SSL_read_ex",   dir: "read",  ex: true  },
        { name: "SSL_write_ex",  dir: "write", ex: true  },
    ];

    // Also try to find SSL_version for protocol detection
    var sslVersionAddr = findExport("SSL_version");
    if (sslVersionAddr === null) {
        sslVersionAddr = findExport("SSL_get_version");
        if (sslVersionAddr !== null) {
            // SSL_get_version returns a string, not int. We need SSL_version.
            // Try string xref approach.
            var alt = findByStringXref("SSL_version");
            if (alt !== null) sslVersionAddr = alt;
            else sslVersionAddr = null;
        }
    }
    if (sslVersionAddr !== null) {
        _SSL_version = new NativeFunction(sslVersionAddr, "int", ["pointer"]);
        log("[+] SSL_version found at " + sslVersionAddr);
    } else {
        log("[!] SSL_version not found -- protocol detection will use heuristics");
    }

    // Install hooks for each target
    for (var i = 0; i < targets.length; i++) {
        var t = targets[i];
        var addr = findExport(t.name);

        // Fallback: string xref scan
        if (addr === null) {
            addr = findByStringXref(t.name);
        }

        if (addr === null) {
            hookStatus(t.name, "not_found");
            log("[-] " + t.name + " not found (export or signature)");
            continue;
        }

        try {
            Interceptor.attach(addr, makeInterceptor(t.name, t.dir, t.ex));
            hookStatus(t.name, "success");
            log("[+] Hooked " + t.name + " at " + addr);
        } catch (e) {
            hookStatus(t.name, "error", e.toString());
            log("[!] Failed to hook " + t.name + ": " + e);
        }
    }

    // Supplementary: try to find and hook SSL_do_handshake for logging
    var hsAddr = findExport("SSL_do_handshake");
    if (hsAddr !== null) {
        try {
            Interceptor.attach(hsAddr, {
                onEnter: function (args) {
                    this.ssl = args[0];
                },
                onLeave: function (retval) {
                    var info = classifySSL(this.ssl);
                    log("[+] SSL_do_handshake completed: ret=" + retval +
                        " protocol=" + info.protocol + " ssl=" + this.ssl);
                }
            });
            hookStatus("SSL_do_handshake", "success");
            log("[+] Hooked SSL_do_handshake at " + hsAddr);
        } catch (e) {
            hookStatus("SSL_do_handshake", "error", e.toString());
        }
    }

    // Hook SSL_new to track new SSL objects
    var sslNewAddr = findExport("SSL_new");
    if (sslNewAddr !== null) {
        try {
            Interceptor.attach(sslNewAddr, {
                onEnter: function (args) {
                    this.ctx = args[0];
                },
                onLeave: function (retval) {
                    if (!retval.isNull()) {
                        log("[+] SSL_new() -> " + retval + " (ctx=" + this.ctx + ")");
                    }
                }
            });
            hookStatus("SSL_new", "success");
            log("[+] Hooked SSL_new at " + sslNewAddr);
        } catch (e) {
            hookStatus("SSL_new", "error", e.toString());
        }
    }

    // Hook SSL_free to clean up our cache
    var sslFreeAddr = findExport("SSL_free");
    if (sslFreeAddr !== null) {
        try {
            Interceptor.attach(sslFreeAddr, {
                onEnter: function (args) {
                    var key = args[0].toString();
                    if (sslContextCache[key] !== undefined) {
                        log("[*] SSL_free(" + key + ") protocol=" + sslContextCache[key].protocol);
                        delete sslContextCache[key];
                    }
                }
            });
            hookStatus("SSL_free", "success");
        } catch (_) {}
    }

    log("=== Hook installation complete ===");
}

// ---------------------------------------------------------------------------
//  Entry point
// ---------------------------------------------------------------------------

// Use setImmediate so the script loads even if hook installation takes a while
setImmediate(function () {
    try {
        installHooks();
    } catch (e) {
        log("[FATAL] Hook installation failed: " + e.stack);
    }
});
