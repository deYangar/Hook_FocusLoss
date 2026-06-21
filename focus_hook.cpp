#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <TlHelp32.h>
#include <MinHook.h>
#include <stdio.h>

#pragma comment(lib, "user32.lib")

// ── 调试日志 ──
static void DebugLog(const char* fmt, ...) {
    char path[MAX_PATH];
    if (GetTempPathA(MAX_PATH, path) == 0) return;
    strcat_s(path, MAX_PATH, "focus_hook_debug.log");

    FILE* f = NULL;
    if (fopen_s(&f, path, "a") != 0 || !f) return;

    SYSTEMTIME st;
    GetLocalTime(&st);
    fprintf(f, "[%04d-%02d-%02d %02d:%02d:%02d.%03d] ",
            st.wYear, st.wMonth, st.wDay, st.wHour, st.wMinute, st.wSecond, st.wMilliseconds);

    va_list args;
    va_start(args, fmt);
    vfprintf(f, fmt, args);
    va_end(args);

    fprintf(f, "\n");
    fclose(f);
}

// ── 全局状态 ──
static HWND g_hwnd = NULL;
static BOOL g_unfocused = FALSE;
static WNDPROC g_origWndProc = NULL;
static DWORD g_initResult = 0;

// ── Hook 原始函数指针 ──
typedef HWND (WINAPI *GetForegroundWindow_t)(void);
typedef HWND (WINAPI *GetFocus_t)(void);
typedef HWND (WINAPI *GetActiveWindow_t)(void);
typedef BOOL (WINAPI *SetCursorPos_t)(int, int);
typedef BOOL (WINAPI *ClipCursor_t)(const RECT*);
typedef int  (WINAPI *ShowCursor_t)(BOOL);
typedef BOOL (WINAPI *GetCursorPos_t)(LPPOINT);
typedef HCURSOR (WINAPI *SetCursor_t)(HCURSOR);

static GetForegroundWindow_t real_GetForegroundWindow = NULL;
static GetFocus_t real_GetFocus = NULL;
static GetActiveWindow_t real_GetActiveWindow = NULL;
static SetCursorPos_t real_SetCursorPos = NULL;
static ClipCursor_t real_ClipCursor = NULL;
static ShowCursor_t real_ShowCursor = NULL;
static GetCursorPos_t real_GetCursorPos = NULL;
static SetCursor_t real_SetCursor = NULL;

static RECT g_clipRect = { 0 };
static BOOL g_clipSet = FALSE;

// ── 窗口枚举：记录所有候选窗口，选最优 ──
struct WinCandidate {
    HWND hwnd;
    int area;
    char title[256];
    BOOL hasTitle;
    BOOL isVisible;
    BOOL isTopLevel;
};

static const int MAX_CANDIDATES = 64;
static WinCandidate g_candidates[MAX_CANDIDATES];
static int g_candidateCount = 0;

static BOOL CALLBACK EnumWindowsCb(HWND hwnd, LPARAM lParam) {
    if (g_candidateCount >= MAX_CANDIDATES) return FALSE;

    WinCandidate* c = &g_candidates[g_candidateCount];

    c->hwnd = hwnd;
    c->hasTitle = FALSE;
    c->isVisible = IsWindowVisible(hwnd);
    c->isTopLevel = (GetWindow(hwnd, GW_OWNER) == NULL);

    char title[256] = {0};
    GetWindowTextA(hwnd, title, sizeof(title));
    strncpy_s(c->title, sizeof(c->title), title, _TRUNCATE);
    c->hasTitle = (strlen(title) > 0);

    RECT rect = { 0 };
    if (GetWindowRect(hwnd, &rect)) {
        c->area = (rect.right - rect.left) * (rect.bottom - rect.top);
    } else {
        c->area = 0;
    }

    g_candidateCount++;
    return TRUE;
}

static HWND GetMainWindow() {
    DWORD currentPid = GetCurrentProcessId();
    g_candidateCount = 0;

    HANDLE hSnap = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
    if (hSnap == INVALID_HANDLE_VALUE) {
        DebugLog("GetMainWindow: CreateToolhelp32Snapshot failed, err=%lu", GetLastError());
        return NULL;
    }

    THREADENTRY32 te = { 0 };
    te.dwSize = sizeof(te);
    int threadCount = 0;

    if (Thread32First(hSnap, &te)) {
        do {
            if (te.th32OwnerProcessID == currentPid) {
                threadCount++;
                EnumThreadWindows(te.th32ThreadID, EnumWindowsCb, 0);
            }
        } while (Thread32Next(hSnap, &te));
    }
    CloseHandle(hSnap);

    DebugLog("GetMainWindow: PID=%lu, 线程数=%d, 候选窗口数=%d", currentPid, threadCount, g_candidateCount);

    // 打印所有候选窗口
    for (int i = 0; i < g_candidateCount; i++) {
        WinCandidate* c = &g_candidates[i];
        DebugLog("  候选[%d]: HWND=0x%p, title='%s', area=%d, visible=%d, topLevel=%d",
                 i, c->hwnd, c->title, c->area, c->isVisible, c->isTopLevel);
    }

    // 选择策略：
    // 1. 优先：有标题 + 可见 + 顶层
    // 2. 其次：可见 + 顶层 + 面积最大
    // 3. 最后：面积最大
    HWND best = NULL;
    int bestScore = -1;

    for (int i = 0; i < g_candidateCount; i++) {
        WinCandidate* c = &g_candidates[i];
        if (!c->isVisible) continue;

        int score = c->area;
        if (c->hasTitle) score += 10000000;  // 有标题权重最高
        if (c->isTopLevel) score += 1000000;

        if (score > bestScore) {
            bestScore = score;
            best = c->hwnd;
        }
    }

    // 如果没找到有标题的，退回面积最大的可见窗口
    if (!best) {
        int maxArea = -1;
        for (int i = 0; i < g_candidateCount; i++) {
            if (g_candidates[i].isVisible && g_candidates[i].area > maxArea) {
                maxArea = g_candidates[i].area;
                best = g_candidates[i].hwnd;
            }
        }
    }

    if (best) {
        char title[256] = {0};
        GetWindowTextA(best, title, sizeof(title));
        DebugLog("GetMainWindow: 选中 HWND=0x%p, title='%s'", best, title);
    } else {
        DebugLog("GetMainWindow: 未找到任何合适窗口!");
    }

    return best;
}

// ── Hook 函数 ──

// GetForegroundWindow → 返回游戏窗口
HWND WINAPI Hook_GetForegroundWindow() {
    return g_hwnd;
}

// GetFocus → 返回游戏窗口（游戏可能用这个检查键盘焦点）
HWND WINAPI Hook_GetFocus() {
    return g_hwnd;
}

// GetActiveWindow → 返回游戏窗口
HWND WINAPI Hook_GetActiveWindow() {
    return g_hwnd;
}

// SetCursorPos → 失焦时阻止游戏强制移动鼠标
BOOL WINAPI Hook_SetCursorPos(int X, int Y) {
    if (g_unfocused) return TRUE;
    return real_SetCursorPos(X, Y);
}

// ClipCursor → 失焦时阻止游戏锁定鼠标在窗口内
BOOL WINAPI Hook_ClipCursor(const RECT* lpRect) {
    if (g_unfocused) {
        // 记录游戏想设的区域，但不实际设置
        if (lpRect) {
            g_clipSet = TRUE;
            g_clipRect = *lpRect;
        } else {
            g_clipSet = FALSE;
        }
        return TRUE;
    }
    return real_ClipCursor(lpRect);
}

// ShowCursor → 失焦时让游戏以为光标是隐藏的
int WINAPI Hook_ShowCursor(BOOL bShow) {
    if (g_unfocused) {
        // 游戏想隐藏光标就让它以为成功了，但不实际操作
        return bShow ? 0 : -1;
    }
    return real_ShowCursor(bShow);
}

// GetCursorPos → 失焦时返回游戏窗口中心附近的坐标，防止游戏检测鼠标离开
BOOL WINAPI Hook_GetCursorPos(LPPOINT lpPoint) {
    if (g_unfocused && g_hwnd) {
        RECT rc;
        if (GetWindowRect(g_hwnd, &rc)) {
            lpPoint->x = (rc.left + rc.right) / 2;
            lpPoint->y = (rc.top + rc.bottom) / 2;
            return TRUE;
        }
    }
    return real_GetCursorPos(lpPoint);
}

static HCURSOR WINAPI Hook_SetCursor(HCURSOR hCursor) {
    if (g_unfocused) {
        return hCursor;
    }
    return real_SetCursor(hCursor);
}

// ── WndProc 替换：吞掉所有失焦消息 ──
LRESULT CALLBACK NewWndProc(HWND hwnd, UINT msg, WPARAM wParam, LPARAM lParam) {
    if (msg == WM_NCACTIVATE && wParam == TRUE) {
        g_unfocused = FALSE;
    }
    else if (msg == WM_NCACTIVATE && wParam == FALSE) {
        g_unfocused = TRUE;
        return 0;
    }
    else if (msg == WM_ACTIVATE) {
        if (LOWORD(wParam) == WA_INACTIVE) {
            return 0;
        }
        // WA_ACTIVE 或 WA_CLICKACTIVE 时标记为有焦点
        g_unfocused = FALSE;
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
    // 额外拦截：鼠标离开窗口区域的消息
    else if (msg == WM_MOUSELEAVE || msg == WM_NCMOUSELEAVE) {
        return 0;
    }
    // 拦截 WM_SETFOCUS 让游戏以为一直有焦点
    else if (msg == WM_SETFOCUS) {
        // 正常传递，游戏需要知道"获得"焦点
    }
    return CallWindowProc(g_origWndProc, hwnd, msg, wParam, lParam);
}

// ── 初始化线程 ──
DWORD WINAPI InitThread(LPVOID) {
    DebugLog("==== InitThread 启动 ====");
    DebugLog("PID=%lu, 架构=%s", GetCurrentProcessId(),
#ifdef _WIN64
             "x64"
#else
             "x86"
#endif
    );

    DebugLog("等待 800ms 让窗口创建...");
    Sleep(800);

    g_hwnd = GetMainWindow();
    if (!g_hwnd) {
        g_initResult = 10;
        DebugLog("[错误] GetMainWindow 返回 NULL, 尝试重试 (额外等待 2000ms)");
        Sleep(2000);
        g_hwnd = GetMainWindow();
        if (!g_hwnd) {
            g_initResult = 11;
            DebugLog("[错误] 重试后仍未找到窗口, 放弃");
            return 1;
        }
        DebugLog("[OK] 重试成功, 找到窗口");
    }

    MH_STATUS mhInit = MH_Initialize();
    DebugLog("MH_Initialize 返回 %d", (int)mhInit);
    if (mhInit != MH_OK && mhInit != MH_ERROR_ALREADY_INITIALIZED) {
        g_initResult = 20;
        DebugLog("[错误] MH_Initialize 失败");
        return 2;
    }

    // Hook 所有焦点相关 API
    struct HookEntry { const char* name; LPVOID target; LPVOID detour; LPVOID* original; };
    HookEntry hooks[] = {
        {"GetForegroundWindow", (LPVOID)GetForegroundWindow, (LPVOID)Hook_GetForegroundWindow, (LPVOID*)&real_GetForegroundWindow},
        {"GetFocus",            (LPVOID)GetFocus,            (LPVOID)Hook_GetFocus,            (LPVOID*)&real_GetFocus},
        {"GetActiveWindow",     (LPVOID)GetActiveWindow,     (LPVOID)Hook_GetActiveWindow,     (LPVOID*)&real_GetActiveWindow},
        {"SetCursorPos",        (LPVOID)SetCursorPos,        (LPVOID)Hook_SetCursorPos,        (LPVOID*)&real_SetCursorPos},
        {"ClipCursor",          (LPVOID)ClipCursor,          (LPVOID)Hook_ClipCursor,          (LPVOID*)&real_ClipCursor},
        {"ShowCursor",          (LPVOID)ShowCursor,          (LPVOID)Hook_ShowCursor,          (LPVOID*)&real_ShowCursor},
        {"GetCursorPos",        (LPVOID)GetCursorPos,        (LPVOID)Hook_GetCursorPos,        (LPVOID*)&real_GetCursorPos},
        {"SetCursor",           (LPVOID)SetCursor,           (LPVOID)Hook_SetCursor,           (LPVOID*)&real_SetCursor},
    };

    int hookCount = 0;
    for (int i = 0; i < sizeof(hooks)/sizeof(hooks[0]); i++) {
        MH_STATUS s = MH_CreateHook(hooks[i].target, hooks[i].detour, hooks[i].original);
        DebugLog("MH_CreateHook(%s) 返回 %d, 原函数=0x%p", hooks[i].name, (int)s, *hooks[i].original);
        if (s == MH_OK) hookCount++;
    }
    DebugLog("成功创建 %d/%d 个 hook", hookCount, (int)(sizeof(hooks)/sizeof(hooks[0])));

    MH_STATUS mhEn = MH_EnableHook(MH_ALL_HOOKS);
    DebugLog("MH_EnableHook(MH_ALL_HOOKS) 返回 %d", (int)mhEn);
    if (mhEn != MH_OK) {
        g_initResult = 30;
        DebugLog("[错误] MH_EnableHook 失败");
        return 3;
    }

    LONG_PTR curProc = GetWindowLongPtr(g_hwnd, GWLP_WNDPROC);
    DebugLog("当前 WndProc=0x%p", (LPVOID)curProc);

    g_origWndProc = (WNDPROC)SetWindowLongPtr(g_hwnd, GWLP_WNDPROC, (LONG_PTR)NewWndProc);
    DWORD err = GetLastError();
    DebugLog("SetWindowLongPtr: 新=0x%p, 旧=0x%p, err=%lu",
             (LPVOID)NewWndProc, (LPVOID)g_origWndProc, err);

    if (!g_origWndProc) {
        g_initResult = 40;
        DebugLog("[错误] SetWindowLongPtr 失败, g_origWndProc=NULL");
        return 4;
    }

    g_initResult = 1;
    DebugLog("[OK] Hook 初始化全部成功! g_hwnd=0x%p, 已 hook %d 个 API", g_hwnd, hookCount);
    return 0;
}

// ── DllMain ──
BOOL APIENTRY DllMain(HMODULE hModule, DWORD reason, LPVOID) {
    switch (reason) {
        case DLL_PROCESS_ATTACH: {
            char dllPath[MAX_PATH] = {0};
            GetModuleFileNameA(hModule, dllPath, MAX_PATH);
            DebugLog("==== DLL_PROCESS_ATTACH ====");
            DebugLog("DLL 路径: %s", dllPath);
            DebugLog("hModule=0x%p", hModule);
            DisableThreadLibraryCalls(hModule);
            CreateThread(NULL, 0, InitThread, NULL, 0, NULL);
            break;
        }
        case DLL_PROCESS_DETACH: {
            DebugLog("==== DLL_PROCESS_DETACH ====");
            DebugLog("g_hwnd=0x%p, g_origWndProc=0x%p, g_initResult=%lu",
                     g_hwnd, (LPVOID)g_origWndProc, g_initResult);

            // 先还原 WndProc
            if (g_hwnd && g_origWndProc) {
                LONG_PTR ret = SetWindowLongPtr(g_hwnd, GWLP_WNDPROC, (LONG_PTR)g_origWndProc);
                DWORD err = GetLastError();
                DebugLog("恢复 WndProc: ret=0x%p, err=%lu", (LPVOID)ret, err);
                g_origWndProc = NULL;
            } else {
                DebugLog("[警告] 跳过 WndProc 恢复: g_hwnd=0x%p, g_origWndProc=0x%p", g_hwnd, (LPVOID)g_origWndProc);
            }

            // 禁用所有 hook
            MH_STATUS s1 = MH_DisableHook(MH_ALL_HOOKS);
            DebugLog("MH_DisableHook 返回 %d", (int)s1);

            // 恢复 ClipCursor
            if (g_clipSet) {
                BOOL cr = ClipCursor(NULL);
                DebugLog("恢复 ClipCursor(NULL) 返回 %d", (int)cr);
                g_clipSet = FALSE;
            }

            MH_STATUS s2 = MH_Uninitialize();
            DebugLog("MH_Uninitialize 返回 %d", (int)s2);

            // 主动发消息让窗口状态刷新
            if (g_hwnd) {
                PostMessageA(g_hwnd, WM_ACTIVATE, MAKELONG(WA_ACTIVE, 0), 0);
                DebugLog("已发送 WM_ACTIVATE(WA_ACTIVE) 刷新窗口状态");
            }

            DebugLog("DLL 卸载完成");
            break;
        }
    }
    return TRUE;
}
