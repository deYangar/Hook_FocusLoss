#!/usr/bin/env python3
"""
Focus Hook Injector
自动检测游戏位数，注入对应 DLL，让游戏以为焦点一直在自己身上。
"""
import ctypes
import ctypes.wintypes as wintypes
import sys
import os
import argparse
import struct

# ── 提权 ──
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

if not is_admin():
    script = os.path.abspath(sys.argv[0])
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{script}" {" ".join(sys.argv[1:])}', None, 1)
    sys.exit()

# ── Win32 API ──
kernel32 = ctypes.windll.kernel32
ntdll = ctypes.windll.ntdll

OpenProcess = kernel32.OpenProcess
OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
OpenProcess.restype = wintypes.HANDLE

VirtualAllocEx = kernel32.VirtualAllocEx
VirtualAllocEx.argtypes = [wintypes.HANDLE, wintypes.LPVOID, ctypes.c_size_t, wintypes.DWORD, wintypes.DWORD]
VirtualAllocEx.restype = wintypes.LPVOID

WriteProcessMemory = kernel32.WriteProcessMemory
WriteProcessMemory.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.LPCVOID, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
WriteProcessMemory.restype = wintypes.BOOL

CreateRemoteThread = kernel32.CreateRemoteThread
CreateRemoteThread.argtypes = [wintypes.HANDLE, wintypes.LPVOID, ctypes.c_size_t, wintypes.LPVOID, wintypes.LPVOID, wintypes.DWORD, wintypes.LPDWORD]
CreateRemoteThread.restype = wintypes.HANDLE

WaitForSingleObject = kernel32.WaitForSingleObject
CloseHandle = kernel32.CloseHandle
GetModuleHandleA = kernel32.GetModuleHandleA
GetProcAddress = kernel32.GetProcAddress

PROCESS_ALL_ACCESS = 0x1F0FFF
MEM_COMMIT = 0x1000
PAGE_READWRITE = 4

# ── 进程枚举 ──
TH32CS_SNAPPROCESS = 0x00000002

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

def find_pid(name: str) -> int:
    hSnap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if hSnap == wintypes.HANDLE(-1):
        return 0
    pe = PROCESSENTRY32()
    pe.dwSize = ctypes.sizeof(pe)
    found = 0
    if kernel32.Process32First(hSnap, ctypes.byref(pe)):
        while True:
            exe = pe.szExeFile.decode('utf-8', errors='ignore').lower().strip('\x00')
            if exe == name.lower():
                found = pe.th32ProcessID
                break
            if not kernel32.Process32Next(hSnap, ctypes.byref(pe)):
                break
    kernel32.CloseHandle(hSnap)
    return found

# ── 检测进程位数 ──
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

def is_process_64bit(pid: int) -> bool:
    """True = 64-bit, False = 32-bit, raises on error."""
    h_process = OpenProcess(PROCESS_ALL_ACCESS, False, pid)
    if not h_process:
        raise OSError(f"OpenProcess failed for PID {pid}")
    
    try:
        # 先检查当前进程是否是 64 位
        si = SYSTEM_INFO()
        kernel32.GetNativeSystemInfo(ctypes.byref(si))
        is_os_64 = si.wProcessorArchitecture in (9, 12)  # x64 or ARM64
        
        if not is_os_64:
            # 32 位系统上所有进程都是 32 位
            return False
        
        # 64 位系统上，用 IsWow64Process 判断
        IsWow64Process = kernel32.IsWow64Process
        IsWow64Process.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
        IsWow64Process.restype = wintypes.BOOL
        
        wow64 = wintypes.BOOL(False)
        if not IsWow64Process(h_process, ctypes.byref(wow64)):
            raise OSError("IsWow64Process failed")
        
        # wow64=True 说明是 32 位进程跑在 64 位系统上（WoW64）
        return not wow64.value
    finally:
        CloseHandle(h_process)

# ── DLL 注入 ──
def inject_dll(pid: int, dll_path: str) -> bool:
    dll_path = os.path.abspath(dll_path)
    if not os.path.exists(dll_path):
        raise FileNotFoundError(f"DLL not found: {dll_path}")
    
    dll_data = dll_path.encode('utf-8') + b'\x00'
    
    h_process = OpenProcess(PROCESS_ALL_ACCESS, False, pid)
    if not h_process:
        raise OSError(f"OpenProcess failed, err={ctypes.get_last_error()}")
    
    try:
        remote_addr = VirtualAllocEx(h_process, None, len(dll_data), MEM_COMMIT, PAGE_READWRITE)
        if not remote_addr:
            raise OSError("VirtualAllocEx failed")
        
        written = ctypes.c_size_t(0)
        if not WriteProcessMemory(h_process, remote_addr, dll_data, len(dll_data), ctypes.byref(written)):
            raise OSError("WriteProcessMemory failed")
        
        loadlib = GetProcAddress(GetModuleHandleA(b"kernel32.dll"), b"LoadLibraryA")
        if not loadlib:
            raise OSError("GetProcAddress(LoadLibraryA) failed")
        
        h_thread = CreateRemoteThread(h_process, None, 0, loadlib, remote_addr, 0, None)
        if not h_thread:
            raise OSError(f"CreateRemoteThread failed, err={ctypes.get_last_error()}")
        
        WaitForSingleObject(h_thread, 0xFFFFFFFF)
        CloseHandle(h_thread)
        return True
    finally:
        CloseHandle(h_process)

# ── 主入口 ──
def main():
    parser = argparse.ArgumentParser(description="让游戏以为自己一直在焦点上")
    parser.add_argument("--game", default="game.exe", help="游戏可执行文件名（如 Game.exe）")
    parser.add_argument("--dll32", default="focus_hook_x86.dll", help="32位 DLL 路径")
    parser.add_argument("--dll64", default="focus_hook_x64.dll", help="64位 DLL 路径")
    args = parser.parse_args()
    
    print(f"[*] 查找进程: {args.game}")
    pid = find_pid(args.game)
    if not pid:
        print(f"[ERR] 找不到进程 '{args.game}'，请确认游戏已启动")
        sys.exit(1)
    print(f"[OK] 找到 {args.game} PID: {pid}")
    
    print("[*] 检测进程位数...")
    is_64 = is_process_64bit(pid)
    bits = 64 if is_64 else 32
    print(f"[OK] 游戏是 {bits} 位")
    
    dll_path = args.dll64 if is_64 else args.dll32
    if not os.path.exists(dll_path):
        # 尝试当前目录
        alt = os.path.join(os.path.dirname(os.path.abspath(__file__)), dll_path)
        if os.path.exists(alt):
            dll_path = alt
    
    print(f"[*] 准备注入: {dll_path}")
    try:
        inject_dll(pid, dll_path)
    except Exception as e:
        print(f"[ERR] 注入失败: {e}")
        sys.exit(1)
    
    print("[OK] 注入成功！游戏现在认为焦点一直在自己身上。")
    print("     你可以 Alt+Tab 切出去干别的了。")

if __name__ == "__main__":
    main()
