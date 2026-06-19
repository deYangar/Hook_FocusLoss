#!/usr/bin/env python3
"""
Focus Hook GUI
直接列出可注入窗口，选择后注入 focus_hook DLL。
"""
import ctypes
import ctypes.wintypes as wintypes
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

# ─────────────────────────────────────────────────────────────
# 管理员权限
# ─────────────────────────────────────────────────────────────
def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False

if not is_admin():
    script = os.path.abspath(sys.argv[0])
    params = " ".join(f'"{x}"' for x in sys.argv[1:])
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{script}" {params}', None, 1)
    sys.exit(0)

# ─────────────────────────────────────────────────────────────
# Win32 API
# ─────────────────────────────────────────────────────────────
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

OpenProcess = kernel32.OpenProcess
OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
OpenProcess.restype = wintypes.HANDLE

VirtualAllocEx = kernel32.VirtualAllocEx
VirtualAllocEx.argtypes = [wintypes.HANDLE, wintypes.LPVOID, ctypes.c_size_t, wintypes.DWORD, wintypes.DWORD]
VirtualAllocEx.restype = wintypes.LPVOID

WriteProcessMemory = kernel32.WriteProcessMemory
WriteProcessMemory.argtypes = [wintypes.HANDLE, wintypes.LPVOID, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
WriteProcessMemory.restype = wintypes.BOOL

CreateRemoteThread = kernel32.CreateRemoteThread
CreateRemoteThread.argtypes = [wintypes.HANDLE, wintypes.LPVOID, ctypes.c_size_t, wintypes.LPVOID, wintypes.LPVOID, wintypes.DWORD, wintypes.LPDWORD]
CreateRemoteThread.restype = wintypes.HANDLE

WaitForSingleObject = kernel32.WaitForSingleObject
WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
WaitForSingleObject.restype = wintypes.DWORD

CloseHandle = kernel32.CloseHandle
CloseHandle.argtypes = [wintypes.HANDLE]
CloseHandle.restype = wintypes.BOOL

GetModuleHandleA = kernel32.GetModuleHandleA
GetModuleHandleA.argtypes = [wintypes.LPCSTR]
GetModuleHandleA.restype = wintypes.HMODULE

GetProcAddress = kernel32.GetProcAddress
GetProcAddress.argtypes = [wintypes.HMODULE, wintypes.LPCSTR]
GetProcAddress.restype = wintypes.LPVOID

GetExitCodeThread = kernel32.GetExitCodeThread
GetExitCodeThread.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
GetExitCodeThread.restype = wintypes.BOOL

Module32First = kernel32.Module32First
Module32First.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
Module32First.restype = wintypes.BOOL

Module32Next = kernel32.Module32Next
Module32Next.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
Module32Next.restype = wintypes.BOOL

PROCESS_ALL_ACCESS = 0x1F0FFF
MEM_COMMIT = 0x1000
MEM_RESERVE = 0x2000
PAGE_READWRITE = 0x04
INFINITE = 0xFFFFFFFF

TH32CS_SNAPPROCESS = 0x00000002
TH32CS_SNAPMODULE = 0x00000008
TH32CS_SNAPMODULE32 = 0x00000010

class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(wintypes.ULONG)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.CHAR * 260),
    ]

class SYSTEM_INFO(ctypes.Structure):
    _fields_ = [
        ("wProcessorArchitecture", wintypes.WORD),
        ("wReserved", wintypes.WORD),
        ("dwPageSize", wintypes.DWORD),
        ("lpMinimumApplicationAddress", wintypes.LPVOID),
        ("lpMaximumApplicationAddress", wintypes.LPVOID),
        ("dwActiveProcessorMask", ctypes.c_void_p),
        ("dwNumberOfProcessors", wintypes.DWORD),
        ("dwProcessorType", wintypes.DWORD),
        ("dwAllocationGranularity", wintypes.DWORD),
        ("wProcessorLevel", wintypes.WORD),
        ("wProcessorRevision", wintypes.WORD),
    ]

class MODULEENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("th32ModuleID", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("GlblcntUsage", wintypes.DWORD),
        ("ProccntUsage", wintypes.DWORD),
        ("modBaseAddr", ctypes.c_void_p),
        ("modBaseSize", wintypes.DWORD),
        ("hModule", wintypes.HMODULE),
        ("szModule", wintypes.CHAR * 256),
        ("szExePath", wintypes.CHAR * 260),
    ]

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

# ─────────────────────────────────────────────────────────────
# 进程 / 窗口枚举
# ─────────────────────────────────────────────────────────────
def build_pid_exe_map():
    pid_map = {}
    h_snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if h_snap == wintypes.HANDLE(-1).value:
        return pid_map

    pe = PROCESSENTRY32()
    pe.dwSize = ctypes.sizeof(pe)
    try:
        if kernel32.Process32First(h_snap, ctypes.byref(pe)):
            while True:
                exe = pe.szExeFile.decode("mbcs", errors="ignore").strip("\x00")
                pid_map[int(pe.th32ProcessID)] = exe
                if not kernel32.Process32Next(h_snap, ctypes.byref(pe)):
                    break
    finally:
        CloseHandle(h_snap)
    return pid_map

def enum_visible_windows():
    """返回 [{'pid', 'exe', 'hwnd', 'title', 'display'}, ...]。只列顶层可见有标题窗口。"""
    pid_map = build_pid_exe_map()
    items = []
    seen_hwnd = set()

    def cb(hwnd, lparam):
        if not user32.IsWindowVisible(hwnd):
            return True

        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True

        title_buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title_buf, length + 1)
        title = title_buf.value.strip()
        if not title:
            return True

        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        pid = int(pid.value)
        exe = pid_map.get(pid, "?")

        # 过滤一部分明显没意义的壳窗口，但不 aggressive，避免漏游戏窗口
        lower_exe = exe.lower()
        if lower_exe in {"shellexperiencehost.exe", "searchhost.exe", "textinputhost.exe"}:
            return True

        hwnd_int = int(hwnd)
        if hwnd_int in seen_hwnd:
            return True
        seen_hwnd.add(hwnd_int)

        display = f"[{exe}] {title}    PID:{pid} HWND:0x{hwnd_int:X}"
        items.append({
            "pid": pid,
            "exe": exe,
            "hwnd": hwnd_int,
            "title": title,
            "display": display,
        })
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    items.sort(key=lambda x: (x["exe"].lower(), x["title"].lower()))
    return items

def is_process_64bit(pid):
    h_process = OpenProcess(PROCESS_ALL_ACCESS, False, pid)
    if not h_process:
        raise OSError(f"OpenProcess failed for PID {pid}, err={ctypes.get_last_error()}")
    try:
        si = SYSTEM_INFO()
        kernel32.GetNativeSystemInfo(ctypes.byref(si))
        is_os_64 = si.wProcessorArchitecture in (9, 12)
        if not is_os_64:
            return False

        IsWow64Process = kernel32.IsWow64Process
        IsWow64Process.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
        IsWow64Process.restype = wintypes.BOOL
        wow64 = wintypes.BOOL(False)
        if not IsWow64Process(h_process, ctypes.byref(wow64)):
            raise OSError(f"IsWow64Process failed, err={ctypes.get_last_error()}")
        return not bool(wow64.value)
    finally:
        CloseHandle(h_process)

def get_base_dir():
    # PyInstaller onefile 会解压到 sys._MEIPASS
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))

def inject_dll(pid, dll_path):
    dll_path = os.path.abspath(dll_path)
    if not os.path.exists(dll_path):
        raise FileNotFoundError(f"DLL not found: {dll_path}")

    dll_data = dll_path.encode("mbcs") + b"\x00"
    h_process = OpenProcess(PROCESS_ALL_ACCESS, False, pid)
    if not h_process:
        raise OSError(f"OpenProcess failed, err={ctypes.get_last_error()}")

    try:
        remote_addr = VirtualAllocEx(h_process, None, len(dll_data), MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE)
        if not remote_addr:
            raise OSError(f"VirtualAllocEx failed, err={ctypes.get_last_error()}")

        written = ctypes.c_size_t(0)
        buf = ctypes.create_string_buffer(dll_data)
        if not WriteProcessMemory(h_process, remote_addr, buf, len(dll_data), ctypes.byref(written)):
            raise OSError(f"WriteProcessMemory failed, err={ctypes.get_last_error()}")

        loadlib = GetProcAddress(GetModuleHandleA(b"kernel32.dll"), b"LoadLibraryA")
        if not loadlib:
            raise OSError(f"GetProcAddress(LoadLibraryA) failed, err={ctypes.get_last_error()}")

        h_thread = CreateRemoteThread(h_process, None, 0, loadlib, remote_addr, 0, None)
        if not h_thread:
            raise OSError(f"CreateRemoteThread failed, err={ctypes.get_last_error()}")

        WaitForSingleObject(h_thread, INFINITE)
        CloseHandle(h_thread)
        return True
    finally:
        CloseHandle(h_process)

def find_remote_module(pid, dll_name):
    """在目标进程里查找已加载 DLL，返回远程 HMODULE。"""
    target = os.path.basename(dll_name).lower()
    flags = TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32
    h_snap = kernel32.CreateToolhelp32Snapshot(flags, pid)
    if h_snap == wintypes.HANDLE(-1).value:
        raise OSError(f"CreateToolhelp32Snapshot(module) failed, err={ctypes.get_last_error()}")

    me = MODULEENTRY32()
    me.dwSize = ctypes.sizeof(me)
    try:
        if not Module32First(h_snap, ctypes.byref(me)):
            return None
        while True:
            name = me.szModule.decode("mbcs", errors="ignore").strip("\x00").lower()
            if name == target:
                return int(me.hModule)
            if not Module32Next(h_snap, ctypes.byref(me)):
                break
    finally:
        CloseHandle(h_snap)
    return None

def unload_dll(pid, dll_name):
    """远程 FreeLibrary 卸载 DLL，触发 DLL_PROCESS_DETACH 还原 Hook。"""
    remote_module = find_remote_module(pid, dll_name)
    if not remote_module:
        raise OSError(f"目标进程里找不到模块：{dll_name}")

    h_process = OpenProcess(PROCESS_ALL_ACCESS, False, pid)
    if not h_process:
        raise OSError(f"OpenProcess failed, err={ctypes.get_last_error()}")

    try:
        freelib = GetProcAddress(GetModuleHandleA(b"kernel32.dll"), b"FreeLibrary")
        if not freelib:
            raise OSError(f"GetProcAddress(FreeLibrary) failed, err={ctypes.get_last_error()}")

        h_thread = CreateRemoteThread(h_process, None, 0, freelib, remote_module, 0, None)
        if not h_thread:
            raise OSError(f"CreateRemoteThread(FreeLibrary) failed, err={ctypes.get_last_error()}")

        try:
            WaitForSingleObject(h_thread, INFINITE)
            code = wintypes.DWORD(0)
            if GetExitCodeThread(h_thread, ctypes.byref(code)) and code.value == 0:
                raise OSError("FreeLibrary 返回失败，Hook 可能仍在目标进程中")
        finally:
            CloseHandle(h_thread)
        return True
    finally:
        CloseHandle(h_process)

# ─────────────────────────────────────────────────────────────
# GUI
# ─────────────────────────────────────────────────────────────
class FocusHookApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Focus Hook")
        self.root.geometry("860x560")
        self.root.minsize(760, 480)

        self.all_windows = []
        self.visible_windows = []
        self.injected = []
        self.current_hook = None
        self.hooking = False

        self._build_ui()
        self.refresh_windows()

    def _build_ui(self):
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill="x")

        ttk.Label(top, text="搜索窗口/进程：").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.apply_filter())
        self.search_entry = ttk.Entry(top, textvariable=self.search_var, width=42)
        self.search_entry.pack(side="left", padx=(6, 10))

        ttk.Button(top, text="刷新窗口", command=self.refresh_windows).pack(side="left", padx=(0, 8))
        self.btn_inject = ttk.Button(top, text="Hook 开始", command=self.start_hook)
        self.btn_inject.pack(side="left", padx=(0, 8))
        self.btn_stop = ttk.Button(top, text="Hook 停止", command=self.stop_hook, state="disabled")
        self.btn_stop.pack(side="left")

        dll_frame = ttk.Frame(self.root, padding=(10, 0, 10, 8))
        dll_frame.pack(fill="x")
        self.dll_status = tk.StringVar()
        ttk.Label(dll_frame, textvariable=self.dll_status, foreground="gray").pack(anchor="w")
        self.update_dll_status()

        main = ttk.PanedWindow(self.root, orient="vertical")
        main.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        win_frame = ttk.LabelFrame(main, text="可注入窗口（直接点选一行）", padding=6)
        main.add(win_frame, weight=3)

        list_frame = ttk.Frame(win_frame)
        list_frame.pack(fill="both", expand=True)
        self.window_list = tk.Listbox(list_frame, activestyle="dotbox", exportselection=False, font=("Consolas", 10))
        self.window_list.pack(side="left", fill="both", expand=True)
        yscroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.window_list.yview)
        yscroll.pack(side="right", fill="y")
        self.window_list.config(yscrollcommand=yscroll.set)
        self.window_list.bind("<Double-Button-1>", lambda e: self.start_hook())

        log_frame = ttk.LabelFrame(main, text="日志", padding=6)
        main.add(log_frame, weight=2)
        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, state="disabled", font=("Consolas", 9), wrap="word")
        self.log_text.pack(fill="both", expand=True)

        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(self.root, textvariable=self.status_var, relief="sunken", anchor="w").pack(fill="x", side="bottom")

    def log(self, msg):
        self.log_text.config(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def update_dll_status(self):
        base = get_base_dir()
        x64 = os.path.join(base, "focus_hook_x64.dll")
        x86 = os.path.join(base, "focus_hook_x86.dll")
        self.dll_status.set(
            f"DLL：x64 {'✓' if os.path.exists(x64) else '✗'}  |  "
            f"x86 {'✓' if os.path.exists(x86) else '✗'}  |  位置：{base}"
        )

    def refresh_windows(self):
        self.all_windows = enum_visible_windows()
        self.apply_filter(select_first=True)
        self.log(f"[刷新] 发现 {len(self.all_windows)} 个可见窗口")
        self.status_var.set(f"发现 {len(self.all_windows)} 个窗口，选择一行后点击 Hook 开始")

    def apply_filter(self, select_first=False):
        keyword = self.search_var.get().strip().lower()
        if keyword:
            self.visible_windows = [
                w for w in self.all_windows
                if keyword in w["display"].lower() or keyword in w["title"].lower() or keyword in w["exe"].lower()
            ]
        else:
            self.visible_windows = list(self.all_windows)

        self.window_list.delete(0, "end")
        for w in self.visible_windows:
            self.window_list.insert("end", w["display"])

        if self.visible_windows and (select_first or self.window_list.curselection() == ()): 
            self.window_list.selection_set(0)
            self.window_list.activate(0)

    def get_selected_window(self):
        sel = self.window_list.curselection()
        if not sel:
            return None
        idx = int(sel[0])
        if idx < 0 or idx >= len(self.visible_windows):
            return None
        return self.visible_windows[idx]

    def start_hook(self):
        if self.hooking:
            return
        w = self.get_selected_window()
        if not w:
            messagebox.showwarning("提示", "先在列表里选择一个窗口")
            return

        pid = w["pid"]
        exe = w["exe"]
        title = w["title"]

        try:
            is64 = is_process_64bit(pid)
        except Exception as e:
            self.log(f"[错误] 检测位数失败：{e}")
            messagebox.showerror("检测失败", str(e))
            return

        bits = 64 if is64 else 32
        dll_name = "focus_hook_x64.dll" if is64 else "focus_hook_x86.dll"
        dll_path = os.path.join(get_base_dir(), dll_name)
        if not os.path.exists(dll_path):
            messagebox.showerror("缺少 DLL", f"找不到 {dll_name}")
            return

        self.hooking = True
        self.btn_inject.config(state="disabled")
        self.status_var.set("注入中...")
        self.log(f"[*] 目标：[{exe}] {title}")
        self.log(f"[*] PID：{pid}，位数：{bits}，DLL：{dll_name}")

        def worker():
            try:
                inject_dll(pid, dll_path)
                hooked = dict(w)
                hooked["dll_name"] = dll_name
                hooked["bits"] = bits
                self.injected.append(hooked)
                self.current_hook = hooked
                self.root.after(0, lambda: self.on_hook_success(hooked, bits))
            except Exception as e:
                self.root.after(0, lambda: self.on_hook_failed(str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def on_hook_success(self, w, bits):
        self.hooking = False
        self.btn_inject.config(state="normal")
        self.btn_stop.config(state="normal")
        self.log("[OK] 注入完成。现在可以切出去测试游戏是否继续运行/出声/响应手柄。")
        self.status_var.set(f"已 Hook：[{w['exe']}] ({bits}位) {w['title']}")

    def on_hook_failed(self, err):
        self.hooking = False
        self.btn_inject.config(state="normal")
        self.log(f"[错误] 注入失败：{err}")
        self.status_var.set("注入失败")
        messagebox.showerror("注入失败", err)

    def stop_hook(self):
        hook = self.current_hook
        if not hook:
            self.btn_stop.config(state="disabled")
            self.status_var.set("当前没有已 Hook 的目标")
            return

        self.btn_stop.config(state="disabled")
        self.status_var.set("正在卸载 Hook...")
        self.log(f"[*] 正在卸载：[{hook['exe']}] {hook['title']} / {hook['dll_name']}")

        def worker():
            try:
                unload_dll(hook["pid"], hook["dll_name"])
                self.root.after(0, lambda: self.on_unhook_success(hook))
            except Exception as e:
                self.root.after(0, lambda: self.on_unhook_failed(str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def on_unhook_success(self, hook):
        self.log("[OK] 已卸载 Hook，目标程序应恢复默认焦点行为。")
        self.current_hook = None
        self.status_var.set(f"已恢复默认：[{hook['exe']}] {hook['title']}")
        self.btn_stop.config(state="disabled")
        self.btn_inject.config(state="normal")

    def on_unhook_failed(self, err):
        self.log(f"[错误] 卸载失败：{err}")
        self.status_var.set("卸载失败；如仍未恢复，请重启目标程序")
        self.btn_stop.config(state="normal")
        messagebox.showerror("卸载失败", err)

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    FocusHookApp().run()
