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

    try {
        var connect = getWs2Export("connect");
        if (connect) {
            Interceptor.attach(connect, {
                onEnter: function (args) {
                    var target = formatSockaddr(args[1]);
                    if (target) {
                        log("[ws2] connect() -> " + target);
                    }
                }
            });
            hookStatus("ws2_connect", "success");
        }

        var sendto = getWs2Export("sendto");
        if (sendto) {
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
        }

        var recvfrom = getWs2Export("recvfrom");
        if (recvfrom) {
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
        }

        var send = getWs2Export("send");
        if (send) {
            Interceptor.attach(send, {
                onEnter: function (args) {
                    this.len = args[2].toInt32();
                },
                onLeave: function (_) {
                    log("[ws2] send -> " + this.len + " bytes");
                }
            });
            hookStatus("ws2_send", "success");
        }

        var recv = getWs2Export("recv");
        if (recv) {
            Interceptor.attach(recv, {
                onLeave: function (retval) {
                    var moved = retval.toInt32();
                    if (moved > 0) {
                        log("[ws2] recv <- " + moved + " bytes");
                    }
                }
            });
            hookStatus("ws2_recv", "success");
        }
    } catch (e) {
        hookStatus("winsock", "error", e.toString());
    }
}

// ---------------------------------------------------------------------------
//  Main hook installation
// ---------------------------------------------------------------------------

function installHooks() {
    log("=== Frida DTLS/TLS Hook for New World ===");
    log("[*] PID: " + Process.id);
    log("[*] Main module: " + getMainModule().name + " @ " + getMainModule().base);
    log("[*] Architecture: " + Process.arch);
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

    // AzNetworking layer
    hookAzNetworking();

    // Winsock connect/sendto for connection target logging
    hookWinsock();

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
