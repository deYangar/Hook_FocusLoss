#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <TlHelp32.h>
#include <MinHook.h>

#pragma comment(lib, "user32.lib")

// ── 全局状态 ──
static HWND g_hwnd = NULL;
static BOOL g_unfocused = FALSE;
static WNDPROC g_origWndProc = NULL;

// ── Hook 原始函数指针 ──
typedef HWND (WINAPI *GetForegroundWindow_t)(void);
typedef BOOL (WINAPI *SetCursorPos_t)(int, int);

static GetForegroundWindow_t real_GetForegroundWindow = GetForegroundWindow;
static SetCursorPos_t real_SetCursorPos = SetCursorPos;

// ── 找到进程的主窗口（面积最大的窗口） ──
struct EnumArgs {
    HWND hwnd;
    int area;
};

static BOOL CALLBACK EnumWindowsCb(HWND hwnd, LPARAM lParam) {
    EnumArgs* args = (EnumArgs*)lParam;
    RECT rect = { 0 };
    GetWindowRect(hwnd, &rect);
    int area = (rect.right - rect.left) * (rect.bottom - rect.top);
    if (area > args->area) {
        args->area = area;
        args->hwnd = hwnd;
    }
    return TRUE;
}

static HWND GetMainWindow() {
    DWORD currentPid = GetCurrentProcessId();
    EnumArgs args = { NULL, -1 };

    HANDLE hSnap = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
    if (hSnap == INVALID_HANDLE_VALUE) return NULL;

    THREADENTRY32 te = { 0 };
    te.dwSize = sizeof(te);

    if (Thread32First(hSnap, &te)) {
        do {
            if (te.th32OwnerProcessID == currentPid) {
                EnumThreadWindows(te.th32ThreadID, EnumWindowsCb, (LPARAM)&args);
            }
        } while (Thread32Next(hSnap, &te));
    }
    CloseHandle(hSnap);
    return args.hwnd;
}

// ── Hook: GetForegroundWindow → 返回游戏自己的窗口 ──
HWND WINAPI Hook_GetForegroundWindow() {
    return g_hwnd;
}

// ── Hook: SetCursorPos → 失焦时阻止鼠标抓取 ──
BOOL WINAPI Hook_SetCursorPos(int X, int Y) {
    if (g_unfocused) return TRUE;
    return real_SetCursorPos(X, Y);
}

// ── WndProc 替换：吞掉所有失焦消息 ──
LRESULT CALLBACK NewWndProc(HWND hwnd, UINT msg, WPARAM wParam, LPARAM lParam) {
    if (msg == WM_NCACTIVATE && wParam == TRUE) {
        g_unfocused = FALSE;
    }
    else if (msg == WM_NCACTIVATE && wParam == FALSE) {
        g_unfocused = TRUE;
        return 0; // 关键：阻断后续 deactivate 消息
    }
    else if (msg == WM_ACTIVATE && wParam == WA_INACTIVE) {
        return 0;
    }
    else if (msg == WM_ACTIVATEAPP && wParam == FALSE) {
        return 0;
    }
    else if (msg == WM_KILLFOCUS) {
        return 0;
    }
    else if (msg == WM_IME_SETCONTEXT && wParam == FALSE) {
        return 0;
    }
    return CallWindowProc(g_origWndProc, hwnd, msg, wParam, lParam);
}

// ── 初始化线程 ──
DWORD WINAPI InitThread(LPVOID) {
    // 等窗口创建出来
    Sleep(800);
    g_hwnd = GetMainWindow();
    if (!g_hwnd) return 1;

    if (MH_Initialize() != MH_OK) return 2;

    MH_CreateHook((LPVOID)GetForegroundWindow, (LPVOID)Hook_GetForegroundWindow, (LPVOID*)&real_GetForegroundWindow);
    MH_CreateHook((LPVOID)SetCursorPos, (LPVOID)Hook_SetCursorPos, (LPVOID*)&real_SetCursorPos);

    if (MH_EnableHook(MH_ALL_HOOKS) != MH_OK) return 3;

    g_origWndProc = (WNDPROC)SetWindowLongPtr(g_hwnd, GWLP_WNDPROC, (LONG_PTR)NewWndProc);
    return 0;
}

// ── DllMain ──
BOOL APIENTRY DllMain(HMODULE hModule, DWORD reason, LPVOID) {
    switch (reason) {
        case DLL_PROCESS_ATTACH:
            DisableThreadLibraryCalls(hModule);
            CreateThread(NULL, 0, InitThread, NULL, 0, NULL);
            break;
        case DLL_PROCESS_DETACH:
            // 卸载时还原 WndProc 和 hook
            if (g_hwnd && g_origWndProc) {
                SetWindowLongPtr(g_hwnd, GWLP_WNDPROC, (LONG_PTR)g_origWndProc);
            }
            MH_DisableHook(MH_ALL_HOOKS);
            MH_Uninitialize();
            break;
    }
    return TRUE;
}
