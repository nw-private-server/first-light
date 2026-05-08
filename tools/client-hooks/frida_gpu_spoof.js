// frida_gpu_spoof.js
//
// Bypass NewWorld's "Unsupported video card detected" abort path so the
// game can proceed past GPU validation in a VM environment where DXGI
// returns VendorId = DeviceId = 0 (e.g. UTM virtio-gpu on Apple Silicon).
//
// The relevant code is in NewWorld.exe FUN_147143960 (binary downloaded
// 2026-05-06). At RVA ~0x147143d2b it calls:
//
//   iVar3 = MessageBoxW((HWND)0x0, pwVar13, L"AZoth", 0x20131);
//   if (iVar3 == 2) {
//       // "User chose to cancel startup due to unsupported GPU."
//       return 0;            // <- caller treats this as fatal
//   }
//
// 0x20131 = MB_OKCANCEL | MB_ICONWARNING | MB_DEFBUTTON2 | MB_SYSTEMMODAL.
// MB_DEFBUTTON2 makes Cancel the default, so an auto-dismissed dialog
// (no human at the keyboard) lands on IDCANCEL = 2 and the game self-
// terminates.
//
// This hook intercepts MessageBoxW and forces the return value to
// IDOK = 1 whenever the caption is the literal "AZoth", which the game
// uses for its own pop-ups. The branch following IDOK falls through to
// "User chose to continue despite unsupported GPU!" and the rest of
// startup proceeds.
//
// Loaded via tools/client-hooks/frida_capture.py --gpu-spoof. The host
// listens for `send({type:"log",...})` messages — console.log is not
// wired up, so this script uses send() everywhere.

(function () {
    function emit(text) {
        send({ type: "log", text: text });
    }

    // Frida 17 dropped the static Module.getExportByName(...) form;
    // use the per-module instance method instead.
    let messageBoxW = null;
    try {
        const mod = Process.getModuleByName("user32.dll");
        if (mod && typeof mod.findExportByName === "function") {
            messageBoxW = mod.findExportByName("MessageBoxW");
        } else if (mod && typeof mod.getExportByName === "function") {
            messageBoxW = mod.getExportByName("MessageBoxW");
        }
    } catch (e) {
        emit("[gpu_spoof] module/export resolution threw: " + e);
    }
    if (!messageBoxW || messageBoxW.isNull()) {
        // last-resort: walk loaded modules and probe for the export
        try {
            const modules = Process.enumerateModules();
            for (let i = 0; i < modules.length; i++) {
                if (modules[i].name.toLowerCase() === "user32.dll") {
                    try {
                        const m = modules[i];
                        if (typeof m.findExportByName === "function") {
                            messageBoxW = m.findExportByName("MessageBoxW");
                        } else if (typeof m.getExportByName === "function") {
                            messageBoxW = m.getExportByName("MessageBoxW");
                        }
                    } catch (_e) {}
                    break;
                }
            }
        } catch (e2) {
            emit("[gpu_spoof] enumerateModules threw: " + e2);
        }
    }
    if (!messageBoxW || messageBoxW.isNull()) {
        emit("[gpu_spoof] could not resolve MessageBoxW; aborting hook install");
        return;
    }
    emit("[gpu_spoof] hooking MessageBoxW @ " + messageBoxW);

    let intercepted = 0;
    let forced = 0;

    Interceptor.attach(messageBoxW, {
        onEnter: function (args) {
            // signature: int MessageBoxW(HWND hWnd, LPCWSTR lpText, LPCWSTR lpCaption, UINT uType)
            try {
                this.caption = args[2].isNull() ? null : args[2].readUtf16String();
                this.text = args[1].isNull() ? null : args[1].readUtf16String();
                this.uType = args[3].toInt32() >>> 0;
            } catch (_e) {
                this.caption = null;
                this.text = null;
            }
            if (this.caption === "AZoth") {
                intercepted += 1;
                var preview = (this.text || "").slice(0, 100).replace(/\r?\n/g, " ");
                emit(
                    "[gpu_spoof] AZoth dialog (uType=0x" +
                        this.uType.toString(16) +
                        "): " +
                        preview +
                        (this.text && this.text.length > 100 ? "..." : "")
                );
            }
        },
        onLeave: function (retval) {
            if (this.caption === "AZoth") {
                var original = retval.toInt32();
                if (original !== 1) {
                    forced += 1;
                    retval.replace(ptr(1));
                    emit(
                        "[gpu_spoof] forced retval " +
                            original +
                            " -> 1 (IDOK); intercepted=" +
                            intercepted +
                            " forced=" +
                            forced
                    );
                } else {
                    emit("[gpu_spoof] AZoth dialog already returned 1 (IDOK), no change");
                }
            }
        },
    });

    emit("[gpu_spoof] hook installed");
})();
