// frida_exit_trap.js
//
// Catch every plausible exit/abort entry point and dump a stack trace.
// Used to identify WHERE the game terminates from when our existing
// hooks (TerminateProcess, abort, RaiseFailFastException, etc.) don't
// fire — see wake 46 for context: FUN_147143960 returns 1 naturally,
// then ~330ms later the process dies silently, with no event in our
// session.log.
//
// The most likely silent-exit paths under Win32 + Frida are:
//
//   1. ntdll!NtTerminateProcess (the syscall stub TerminateProcess
//      eventually calls — direct callers bypass kernel32 hooks)
//   2. ntdll!RtlExitUserProcess (the orderly C-runtime exit path)
//   3. KERNELBASE!UnhandledExceptionFilter (Windows' last-chance
//      exception handler that ends with TerminateProcess)
//   4. ntdll!KiUserExceptionDispatcher (kernel-to-user exception
//      delivery — fires for access violations, the most likely
//      cause of a "broken renderer dereferences null" abort)
//   5. kernel32!RaiseException (explicit C++ throw / SEH raise)
//
// Each hook prints a stack trace on entry. The first one to fire
// names the source.

(function () {
    function emit(text) {
        send({ type: "log", text: text });
    }

    function backtrace(ctx, label) {
        // Try ACCURATE first for clean prologues; fall back to FUZZY which
        // copes better with hand-written assembly / exception dispatchers
        // where ACCURATE gives up at the first frame.
        const tries = [Backtracer.ACCURATE, Backtracer.FUZZY];
        for (let t = 0; t < tries.length; t++) {
            try {
                const frames = Thread.backtrace(ctx, tries[t]);
                if (!frames || frames.length === 0) continue;
                const tag = tries[t] === Backtracer.ACCURATE ? "ACCURATE" : "FUZZY";
                emit(
                    "[exit_trap] " +
                        label +
                        " stack[" +
                        tag +
                        "] (" +
                        frames.length +
                        " frames):"
                );
                for (let i = 0; i < frames.length && i < 32; i++) {
                    let sym;
                    try {
                        sym = DebugSymbol.fromAddress(frames[i]).toString();
                    } catch (_e) {
                        sym = "(no symbol)";
                    }
                    emit("    " + i + ". " + frames[i] + "  " + sym);
                }
                if (frames.length > 1) return; // good enough
            } catch (e) {
                emit("[exit_trap] backtrace " + t + " failed: " + e);
            }
        }
    }

    // Decode EXCEPTION_RECORD on x64 Windows.
    //   typedef struct _EXCEPTION_RECORD {
    //       DWORD                    ExceptionCode;        // 0x00
    //       DWORD                    ExceptionFlags;       // 0x04
    //       struct _EXCEPTION_RECORD *ExceptionRecord;     // 0x08
    //       PVOID                    ExceptionAddress;     // 0x10
    //       DWORD                    NumberParameters;     // 0x18
    //       ULONG_PTR                ExceptionInformation[15]; // 0x20
    //   } EXCEPTION_RECORD;
    function readExceptionRecord(ptrER, label) {
        try {
            if (!ptrER || ptrER.isNull()) {
                emit("[exit_trap] " + label + " EXCEPTION_RECORD null");
                return;
            }
            const code = ptrER.readU32();
            const flags = ptrER.add(4).readU32();
            const exAddr = ptrER.add(0x10).readPointer();
            const numParams = ptrER.add(0x18).readU32();
            let sym = "(no symbol)";
            try {
                sym = DebugSymbol.fromAddress(exAddr).toString();
            } catch (_e) {}
            emit(
                "[exit_trap] " +
                    label +
                    " EXCEPTION code=0x" +
                    code.toString(16) +
                    " flags=0x" +
                    flags.toString(16) +
                    " addr=" +
                    exAddr +
                    " (" +
                    sym +
                    ") nparams=" +
                    numParams
            );
            for (let i = 0; i < numParams && i < 4; i++) {
                const v = ptrER.add(0x20 + i * 8).readPointer();
                emit("    param[" + i + "] = " + v);
            }
        } catch (e) {
            emit("[exit_trap] " + label + " EXCEPTION_RECORD read failed: " + e);
        }
    }

    function tryHook(modName, exportName, dumpArgs) {
        try {
            const mod = Process.getModuleByName(modName);
            if (!mod) {
                emit("[exit_trap] module " + modName + " not loaded; skip " + exportName);
                return;
            }
            let addr;
            if (typeof mod.findExportByName === "function") {
                addr = mod.findExportByName(exportName);
            } else if (typeof mod.getExportByName === "function") {
                addr = mod.getExportByName(exportName);
            }
            if (!addr || addr.isNull()) {
                emit("[exit_trap] " + modName + "!" + exportName + " not found");
                return;
            }
            Interceptor.attach(addr, {
                onEnter: function (args) {
                    let argDump = "";
                    if (dumpArgs > 0) {
                        const parts = [];
                        for (let i = 0; i < dumpArgs; i++) {
                            parts.push("arg" + i + "=" + args[i]);
                        }
                        argDump = " " + parts.join(" ");
                    }
                    emit(
                        "[exit_trap] *** " +
                            modName +
                            "!" +
                            exportName +
                            argDump +
                            " (tid=" +
                            this.threadId +
                            ")"
                    );
                    backtrace(this.context, modName + "!" + exportName);
                },
            });
            emit("[exit_trap] hooked " + modName + "!" + exportName + " @ " + addr);
        } catch (e) {
            emit("[exit_trap] hook " + modName + "!" + exportName + " threw: " + e);
        }
    }

    // Special hook: KiUserExceptionDispatcher gets the EXCEPTION_RECORD
    // via the rcx register on x64 Windows (not standard arg passing).
    // It's the kernel-to-user transition point for hardware exceptions.
    try {
        const mod = Process.getModuleByName("ntdll.dll");
        const addr =
            (mod && (mod.findExportByName ? mod.findExportByName("KiUserExceptionDispatcher")
                                          : mod.getExportByName("KiUserExceptionDispatcher")));
        if (addr && !addr.isNull()) {
            Interceptor.attach(addr, {
                onEnter: function (_args) {
                    emit(
                        "[exit_trap] *** ntdll!KiUserExceptionDispatcher (tid=" +
                            this.threadId +
                            ")"
                    );
                    // On x64, the dispatcher receives EXCEPTION_RECORD* in rcx
                    // and CONTEXT* in rdx. Frida's args[] array maps to rcx/rdx/r8/r9.
                    // The exception record is also reachable via the CPU context.
                    try {
                        const recordPtr = this.context.rcx; // first arg on x64
                        const ctxPtr = this.context.rdx; // CONTEXT*
                        readExceptionRecord(recordPtr, "KiUserExceptionDispatcher");
                        // The CONTEXT struct's RIP at offset 0xF8 is where the fault occurred
                        try {
                            const faultRip = ctxPtr.add(0xf8).readPointer();
                            let sym = "(no symbol)";
                            try {
                                sym = DebugSymbol.fromAddress(faultRip).toString();
                            } catch (_e) {}
                            emit(
                                "[exit_trap]   CONTEXT.Rip = " + faultRip + " (" + sym + ")"
                            );
                        } catch (_e) {}
                    } catch (e) {
                        emit("[exit_trap] could not read exception record: " + e);
                    }
                    backtrace(this.context, "KiUserExceptionDispatcher");
                },
            });
            emit("[exit_trap] hooked ntdll!KiUserExceptionDispatcher (special) @ " + addr);
        } else {
            emit("[exit_trap] KiUserExceptionDispatcher not found");
        }
    } catch (e) {
        emit("[exit_trap] KiUserExceptionDispatcher special hook threw: " + e);
    }

    // Direct termination paths.
    tryHook("ntdll.dll", "NtTerminateProcess", 2);
    tryHook("ntdll.dll", "RtlExitUserProcess", 1);
    tryHook("ntdll.dll", "ZwTerminateProcess", 2); // alias of Nt*; hook both in case one isn't reached
    tryHook("ntdll.dll", "RtlRaiseStatus", 1);

    // Exception-driven abort paths (other than KiUserExceptionDispatcher which
    // has its special hook above).
    tryHook("ntdll.dll", "RtlDispatchException", 2);
    tryHook("KernelBase.dll", "UnhandledExceptionFilter", 1);
    tryHook("KernelBase.dll", "RaiseException", 1);
    tryHook("kernel32.dll", "UnhandledExceptionFilter", 1);
    tryHook("kernel32.dll", "RaiseException", 1);

    // C-runtime aborts (in case the engine bundles its own VC runtime).
    tryHook("ucrtbase.dll", "abort", 0);
    tryHook("ucrtbase.dll", "_exit", 1);
    tryHook("ucrtbase.dll", "exit", 1);
    tryHook("vcruntime140.dll", "_CxxThrowException", 2);

    // Entry-time hook on FUN_1410d1120 (the function that crashes
    // ~332ms after FUN_147143960 returns; wake 47 root-cause). Captures
    // a backtrace at every call so we can identify the calling
    // subsystem before the crash strikes.
    try {
        const main = Process.getModuleByName("NewWorld.exe");
        if (main) {
            const RVA_CRASH_FN = 0x10d1120;
            const crashFnAddr = main.base.add(RVA_CRASH_FN);
            let calls = 0;
            Interceptor.attach(crashFnAddr, {
                onEnter: function (args) {
                    calls += 1;
                    // Sample first 4 entries so we don't flood; the crash
                    // happens on the nth call where n is small.
                    if (calls <= 4 || calls % 100 === 0) {
                        emit(
                            "[exit_trap] FUN_1410d1120 entered (call #" +
                                calls +
                                " tid=" +
                                this.threadId +
                                ")"
                        );
                        emit(
                            "[exit_trap]   args: arg0=" +
                                args[0] +
                                " arg1=" +
                                args[1] +
                                " arg2=" +
                                args[2]
                        );
                        backtrace(this.context, "FUN_1410d1120 entry call#" + calls);
                    }
                },
            });
            emit(
                "[exit_trap] hooked FUN_1410d1120 (crash site) @ " +
                    crashFnAddr +
                    " (base=" +
                    main.base +
                    " + 0x" +
                    RVA_CRASH_FN.toString(16) +
                    ")"
            );
        }
    } catch (e) {
        emit("[exit_trap] FUN_1410d1120 entry hook threw: " + e);
    }

    emit("[exit_trap] all hooks installed");
})();
