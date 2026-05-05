#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <d3d11.h>
#include <cstdio>
#include <cstring>
#include <cstdint>
#include <mutex>

namespace {

constexpr uintptr_t kPatchRva = 0x05dce8b5;
constexpr unsigned char kExpected[] = {0x0F, 0x84, 0x19, 0x01, 0x00, 0x00};
constexpr unsigned char kPatched[]  = {0xE9, 0x19, 0x01, 0x00, 0x00, 0x90};

HMODULE g_real = nullptr;
std::once_flag g_init_once;

void log_line(const char* text) {
    char temp_path[MAX_PATH] = {};
    if (GetTempPathA(MAX_PATH, temp_path) == 0) {
        return;
    }
    char path[MAX_PATH] = {};
    std::snprintf(path, sizeof(path), "%snw_d3d11_proxy.log", temp_path);
    FILE* fp = nullptr;
    fopen_s(&fp, path, "a");
    if (!fp) return;
    std::fprintf(fp, "%s\n", text);
    std::fclose(fp);
}

void ensure_real_loaded() {
    std::call_once(g_init_once, [] {
        char system_dir[MAX_PATH] = {};
        if (GetSystemDirectoryA(system_dir, MAX_PATH) == 0) {
            log_line("[!] GetSystemDirectoryA failed");
            return;
        }

        char path[MAX_PATH] = {};
        std::snprintf(path, sizeof(path), "%s\\d3d11.dll", system_dir);
        g_real = LoadLibraryA(path);
        if (g_real) {
            log_line("[*] Loaded real system d3d11.dll");
        } else {
            log_line("[!] Failed to load real system d3d11.dll");
        }
    });
}

FARPROC resolve_export(const char* name) {
    ensure_real_loaded();
    if (!g_real) {
        return nullptr;
    }
    return GetProcAddress(g_real, name);
}

void apply_dtls_patch() {
    HMODULE main_mod = GetModuleHandleW(nullptr);
    if (!main_mod) {
        log_line("[!] GetModuleHandleW(nullptr) failed");
        return;
    }

    auto* target = reinterpret_cast<unsigned char*>(
        reinterpret_cast<uintptr_t>(main_mod) + kPatchRva);

    if (std::memcmp(target, kPatched, sizeof(kPatched)) == 0) {
        log_line("[*] DTLS trust patch already applied");
        return;
    }

    if (std::memcmp(target, kExpected, sizeof(kExpected)) != 0) {
        log_line("[!] Unexpected bytes at DTLS trust patch site");
        return;
    }

    DWORD old_protect = 0;
    if (!VirtualProtect(target, sizeof(kPatched), PAGE_EXECUTE_READWRITE, &old_protect)) {
        log_line("[!] VirtualProtect failed for DTLS trust patch");
        return;
    }

    std::memcpy(target, kPatched, sizeof(kPatched));
    FlushInstructionCache(GetCurrentProcess(), target, sizeof(kPatched));

    DWORD ignored = 0;
    VirtualProtect(target, sizeof(kPatched), old_protect, &ignored);
    log_line("[+] Applied DTLS trust patch");
}

template <typename T>
T load(const char* name) {
    return reinterpret_cast<T>(resolve_export(name));
}

using PFN_D3D11CreateDevice = HRESULT (WINAPI*)(
    IDXGIAdapter*, D3D_DRIVER_TYPE, HMODULE, UINT,
    const D3D_FEATURE_LEVEL*, UINT, UINT,
    ID3D11Device**, D3D_FEATURE_LEVEL*, ID3D11DeviceContext**);

using PFN_D3D11CreateDeviceAndSwapChain = HRESULT (WINAPI*)(
    IDXGIAdapter*, D3D_DRIVER_TYPE, HMODULE, UINT,
    const D3D_FEATURE_LEVEL*, UINT, UINT,
    const DXGI_SWAP_CHAIN_DESC*, IDXGISwapChain**,
    ID3D11Device**, D3D_FEATURE_LEVEL*, ID3D11DeviceContext**);

using PFN_D3D11CoreCreateDevice = HRESULT (WINAPI*)(
    IDXGIFactory*, IDXGIAdapter*, UINT, const void*, void**);
using PFN_D3D11CoreCreateLayeredDevice = HRESULT (WINAPI*)(
    const void*, DWORD, const void*, REFIID, void**);
using PFN_D3D11CoreGetLayeredDeviceSize = SIZE_T (WINAPI*)(
    const void*, DWORD);
using PFN_D3D11CoreRegisterLayers = HRESULT (WINAPI*)(
    const void*, DWORD);
using PFN_D3DPerformance_BeginEvent = int (WINAPI*)(LPCWSTR);
using PFN_D3DPerformance_EndEvent = int (WINAPI*)();
using PFN_D3DPerformance_GetStatus = DWORD (WINAPI*)();
using PFN_D3DPerformance_SetMarker = void (WINAPI*)(LPCWSTR);

}  // namespace

extern "C" HRESULT WINAPI D3D11CreateDevice(
    IDXGIAdapter* a, D3D_DRIVER_TYPE b, HMODULE c, UINT d,
    const D3D_FEATURE_LEVEL* e, UINT f, UINT g,
    ID3D11Device** h, D3D_FEATURE_LEVEL* i, ID3D11DeviceContext** j) {
    auto fn = load<PFN_D3D11CreateDevice>("D3D11CreateDevice");
    return fn ? fn(a, b, c, d, e, f, g, h, i, j) : E_FAIL;
}

extern "C" HRESULT WINAPI D3D11CreateDeviceAndSwapChain(
    IDXGIAdapter* a, D3D_DRIVER_TYPE b, HMODULE c, UINT d,
    const D3D_FEATURE_LEVEL* e, UINT f, UINT g,
    const DXGI_SWAP_CHAIN_DESC* h, IDXGISwapChain** i,
    ID3D11Device** j, D3D_FEATURE_LEVEL* k, ID3D11DeviceContext** l) {
    auto fn = load<PFN_D3D11CreateDeviceAndSwapChain>("D3D11CreateDeviceAndSwapChain");
    return fn ? fn(a, b, c, d, e, f, g, h, i, j, k, l) : E_FAIL;
}

extern "C" HRESULT WINAPI D3D11CoreCreateDevice(
    IDXGIFactory* a, IDXGIAdapter* b, UINT c, const void* d, void** e) {
    auto fn = load<PFN_D3D11CoreCreateDevice>("D3D11CoreCreateDevice");
    return fn ? fn(a, b, c, d, e) : E_FAIL;
}

extern "C" HRESULT WINAPI D3D11CoreCreateLayeredDevice(
    const void* a, DWORD b, const void* c, REFIID d, void** e) {
    auto fn = load<PFN_D3D11CoreCreateLayeredDevice>("D3D11CoreCreateLayeredDevice");
    return fn ? fn(a, b, c, d, e) : E_FAIL;
}

extern "C" SIZE_T WINAPI D3D11CoreGetLayeredDeviceSize(
    const void* a, DWORD b) {
    auto fn = load<PFN_D3D11CoreGetLayeredDeviceSize>("D3D11CoreGetLayeredDeviceSize");
    return fn ? fn(a, b) : 0;
}

extern "C" HRESULT WINAPI D3D11CoreRegisterLayers(
    const void* a, DWORD b) {
    auto fn = load<PFN_D3D11CoreRegisterLayers>("D3D11CoreRegisterLayers");
    return fn ? fn(a, b) : E_FAIL;
}

extern "C" int WINAPI D3DPerformance_BeginEvent(LPCWSTR a) {
    auto fn = load<PFN_D3DPerformance_BeginEvent>("D3DPerformance_BeginEvent");
    return fn ? fn(a) : -1;
}

extern "C" int WINAPI D3DPerformance_EndEvent() {
    auto fn = load<PFN_D3DPerformance_EndEvent>("D3DPerformance_EndEvent");
    return fn ? fn() : -1;
}

extern "C" DWORD WINAPI D3DPerformance_GetStatus() {
    auto fn = load<PFN_D3DPerformance_GetStatus>("D3DPerformance_GetStatus");
    return fn ? fn() : 0;
}

extern "C" void WINAPI D3DPerformance_SetMarker(LPCWSTR a) {
    auto fn = load<PFN_D3DPerformance_SetMarker>("D3DPerformance_SetMarker");
    if (fn) fn(a);
}

BOOL WINAPI DllMain(HINSTANCE module, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(module);
        ensure_real_loaded();
        apply_dtls_patch();
    }
    return TRUE;
}
