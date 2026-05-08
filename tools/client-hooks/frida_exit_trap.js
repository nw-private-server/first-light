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
        try {
            const frames = Thread.backtrace(ctx, Backtracer.ACCURATE);
            const lines = [];
            for (let i = 0; i < frames.length && i < 32; i++) {
                let sym;
                try {
                    sym = DebugSymbol.fromAddress(frames[i]).toString();
                } catch (_e) {
                    sym = frames[i].toString();
                }
                lines.push("    " + i + ". " + frames[i] + "  " + sym);
            }
            emit("[exit_trap] " + label + " stack (" + frames.length + " frames):");
            for (let i = 0; i < lines.length; i++) emit(lines[i]);
        } catch (e) {
            emit("[exit_trap] backtrace failed: " + e);
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

    // Direct termination paths.
    tryHook("ntdll.dll", "NtTerminateProcess", 2);
    tryHook("ntdll.dll", "RtlExitUserProcess", 1);
    tryHook("ntdll.dll", "ZwTerminateProcess", 2); // alias of Nt*; hook both in case one isn't reached
    tryHook("ntdll.dll", "RtlRaiseStatus", 1);

    // Exception-driven abort paths.
    tryHook("ntdll.dll", "KiUserExceptionDispatcher", 0);
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

    emit("[exit_trap] all hooks installed");
})();
