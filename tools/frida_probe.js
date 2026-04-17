/**
 * Lightweight probe script — enumerate all modules and search for SSL exports.
 * Run this first to find where OpenSSL functions live in memory.
 */
"use strict";

function log(text) {
    send({ type: "log", text: text });
}

// 1. Enumerate all loaded modules
log("=== Loaded Modules ===");
var modules = Process.enumerateModules();
log("Total modules: " + modules.length);

// Look for SSL-related modules
modules.forEach(function(m) {
    var nameLower = m.name.toLowerCase();
    if (nameLower.indexOf("ssl") !== -1 || nameLower.indexOf("crypto") !== -1 ||
        nameLower.indexOf("tls") !== -1 || nameLower.indexOf("boring") !== -1 ||
        nameLower.indexOf("openssl") !== -1 || nameLower.indexOf("schannel") !== -1 ||
        nameLower.indexOf("secur") !== -1 || nameLower.indexOf("newworld") !== -1) {
        log("  [*] " + m.name + "  base=" + m.base + "  size=0x" + m.size.toString(16));
    }
});

// 2. Search ALL modules for SSL exports
log("\n=== Searching for SSL exports in all modules ===");
var sslTargets = ["SSL_read", "SSL_write", "SSL_read_ex", "SSL_write_ex",
                  "SSL_do_handshake", "SSL_CTX_new", "SSL_new", "SSL_free",
                  "SSL_version", "SSL_get_version", "SSL_connect", "SSL_accept",
                  "DTLS_method", "DTLSv1_2_method", "DTLS_client_method",
                  "BIO_read", "BIO_write",
                  "OPENSSL_init_ssl", "SSL_library_init"];

modules.forEach(function(m) {
    var exports = m.enumerateExports();
    exports.forEach(function(exp) {
        for (var i = 0; i < sslTargets.length; i++) {
            if (exp.name === sslTargets[i]) {
                log("  FOUND: " + exp.name + " in " + m.name + " @ " + exp.address);
            }
        }
    });
});

// 3. Try resolving by name in case they're in the main exe or IAT
log("\n=== Trying Module.findExportByName for SSL functions ===");
sslTargets.forEach(function(name) {
    var addr = Module.findExportByName(null, name);
    if (addr) {
        log("  FOUND: " + name + " @ " + addr);
        // Find which module this belongs to
        var mod = Process.findModuleByAddress(addr);
        if (mod) {
            log("         in module: " + mod.name);
        }
    }
});

// 4. Check Windows crypto DLLs
log("\n=== Checking Windows crypto APIs ===");
var winCrypto = ["ncrypt.dll", "bcrypt.dll", "schannel.dll", "crypt32.dll", "secur32.dll"];
winCrypto.forEach(function(dll) {
    try {
        var mod = Process.getModuleByName(dll);
        if (mod) {
            log("  Loaded: " + dll + "  base=" + mod.base + "  size=0x" + mod.size.toString(16));
            // Check for SChannel/SSPI functions
            var sspiTargets = ["SslEncryptPacket", "SslDecryptPacket",
                              "EncryptMessage", "DecryptMessage",
                              "InitializeSecurityContextW", "AcceptSecurityContext"];
            var exports = mod.enumerateExports();
            exports.forEach(function(exp) {
                for (var i = 0; i < sspiTargets.length; i++) {
                    if (exp.name === sspiTargets[i]) {
                        log("    FOUND: " + exp.name + " @ " + exp.address);
                    }
                }
            });
        }
    } catch(_) {}
});

// 5. Search for OpenSSL strings in memory as a last resort
log("\n=== Searching for OpenSSL version string in NewWorld.exe memory ===");
try {
    var mainMod = Process.enumerateModules()[0];
    var ranges = mainMod.enumerateRanges("r--");
    var found = false;
    for (var i = 0; i < ranges.length && !found; i++) {
        try {
            var results = Memory.scanSync(ranges[i].base, ranges[i].size, "4f 70 65 6e 53 53 4c 20"); // "OpenSSL "
            results.forEach(function(match) {
                var str = match.address.readUtf8String(64);
                log("  OpenSSL version string at " + match.address + ": " + str);
                found = true;
            });
        } catch(_) {}
    }
    if (!found) log("  Not found in readable ranges");
} catch(e) {
    log("  Error scanning: " + e);
}

// 6. Look for AWS SDK / Cognito / STS functions
log("\n=== Searching for AWS/game-specific exports ===");
var gameTargets = ["AzNetworking", "Javelin", "Campfire", "GameConnection", "REP"];
modules.forEach(function(m) {
    if (m.name.toLowerCase() === "newworld.exe") {
        var exports = m.enumerateExports();
        var count = 0;
        exports.forEach(function(exp) {
            for (var i = 0; i < gameTargets.length; i++) {
                if (exp.name.indexOf(gameTargets[i]) !== -1) {
                    log("  FOUND: " + exp.name + " @ " + exp.address);
                    count++;
                    if (count > 30) return;
                }
            }
        });
        log("  Total exports in NewWorld.exe: " + exports.length);
    }
});

log("\n=== Probe complete ===");
