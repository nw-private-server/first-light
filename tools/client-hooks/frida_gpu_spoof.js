// frida_gpu_spoof.js
//
// Bypass NewWorld's GPU-validation abort path so the game can proceed
// past adapter detection in a VM environment where DXGI returns
// VendorId = DeviceId = 0 (e.g. UTM virtio-gpu on Apple Silicon).
//
// The relevant code is in NewWorld.exe FUN_147143960 (RVA 0x7143960
// from image base 0x140000000; binary downloaded 2026-05-06). It:
//
//   1. Gathers GPU info via FUN_1470b99f0
//   2. If feature level < 6, shows MessageBoxW(AZoth, 0x20131)
//      asking user to continue or cancel — if cancel, returns 0
//   3. Initializes the chosen Render Module (D3D11 or D3D12) via
//      a vtable call (param_1[0x4b8]) — if init fails, returns 0
//   4. Returns 1 on full success
//
// The CALLER treats a 0 return as fatal and TerminateProcess()es.
//
// Two hooks here, layered:
//
// (a) MessageBoxW interceptor — forces IDOK on any AZoth-captioned
//     dialog. In testing on Frida 17, the dialog was already auto-
//     dismissing as IDOK so this is mostly defensive.
//
// (b) FUN_147143960 onLeave override — forces retval = 1 even when
//     render-module init fails. The game's renderer won't actually
//     work, but we don't need rendering for network init; networking
//     runs on its own thread and reaches V3 RegistrationRequest
//     independently of the render path. Keeping the process alive
//     past validateGpu() is enough.
//
// Loaded via tools/client-hooks/frida_capture.py --gpu-spoof. The host
// listens for `send({type:"log",...})` messages — console.log is not
// wired up, so this script uses send() everywhere.

const RVA_VALIDATE_GPU = 0x7143960;

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

    emit("[gpu_spoof] MessageBoxW hook installed");

    // (b) Hook FUN_147143960 (validateGpu) and force its retval to 1
    //     even when D3D11 init fails. This keeps the process alive
    //     past the GPU gate so network init can proceed.
    try {
        const mainModule = Process.getModuleByName("NewWorld.exe");
        if (!mainModule) {
            emit("[gpu_spoof] could not get NewWorld.exe module; FUN_147143960 hook skipped");
            return;
        }
        const validateGpuAddr = mainModule.base.add(RVA_VALIDATE_GPU);
        emit(
            "[gpu_spoof] hooking FUN_147143960 @ " +
                validateGpuAddr +
                " (base=" +
                mainModule.base +
                " + 0x" +
                RVA_VALIDATE_GPU.toString(16) +
                ")"
        );

        let validateCalls = 0;
        let validateForced = 0;
        Interceptor.attach(validateGpuAddr, {
            onEnter: function (_args) {
                validateCalls += 1;
                emit("[gpu_spoof] FUN_147143960 entered (call #" + validateCalls + ")");
            },
            onLeave: function (retval) {
                const orig = retval.toInt32();
                if (orig !== 1) {
                    validateForced += 1;
                    retval.replace(ptr(1));
                    emit(
                        "[gpu_spoof] FUN_147143960 retval " +
                            orig +
                            " -> 1 (forced; calls=" +
                            validateCalls +
                            " forced=" +
                            validateForced +
                            ")"
                    );
                } else {
                    emit("[gpu_spoof] FUN_147143960 returned 1 naturally");
                }
            },
        });
        emit("[gpu_spoof] FUN_147143960 hook installed");
    } catch (e) {
        emit("[gpu_spoof] FUN_147143960 hook setup threw: " + e);
    }
})();
