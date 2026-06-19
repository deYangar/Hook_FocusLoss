#!/usr/bin/env python3
"""
自动搜索 g++ 并编译 focus_hook DLL（32位 + 64位）
双击运行即可，不需要 PowerShell 执行策略
"""
import os
import sys
import subprocess
import glob

BASE = os.path.dirname(os.path.abspath(__file__))

# 常见 g++ 位置
COMMON_PATHS = [
    r"C:\mingw64\bin\g++.exe",
    r"C:\mingw32\bin\g++.exe",
    r"C:\msys64\mingw64\bin\g++.exe",
    r"C:\msys64\mingw32\bin\g++.exe",
    r"C:\TDM-GCC-64\bin\g++.exe",
    r"C:\Program Files\mingw-w64\x86_64-8.1.0-posix-seh-rt_v6-rev0\mingw64\bin\g++.exe",
    r"C:\Program Files (x86)\mingw-w64\i686-8.1.0-posix-dwarf-rt_v6-rev0\mingw32\bin\g++.exe",
    r"C:\Program Files\CodeBlocks\MinGW\bin\g++.exe",
    r"C:\Program Files (x86)\Dev-Cpp\MinGW64\bin\g++.exe",
    r"C:\Program Files (x86)\Dev-Cpp\MinGW32\bin\g++.exe",
    r"C:\Qt\Tools\mingw810_64\bin\g++.exe",
    r"C:\Qt\Tools\mingw810_32\bin\g++.exe",
]

def find_gpp():
    """搜索 g++.exe"""
    # 1. 检查 PATH
    try:
        result = subprocess.run(["where", "g++"], capture_output=True, text=True, shell=True)
        if result.returncode == 0:
            path = result.stdout.strip().splitlines()[0].strip()
            if os.path.exists(path):
                return path
    except Exception:
        pass
    
    # 2. 检查常见路径
    for p in COMMON_PATHS:
        if os.path.exists(p):
            return p
    
    # 3. 快速扫描 Program Files 下的 mingw
    for root in [r"C:\Program Files", r"C:\Program Files (x86)", "C:\\"]:
        if not os.path.exists(root):
            continue
        # 只扫描一层子目录，避免太慢
        for item in os.listdir(root):
            item_path = os.path.join(root, item)
            if os.path.isdir(item_path) and "mingw" in item.lower():
                for sub in os.listdir(item_path):
                    candidate = os.path.join(item_path, sub, "bin", "g++.exe")
                    if os.path.exists(candidate):
                        return candidate
                    # 有的结构是 mingw64/bin/g++.exe
                    candidate2 = os.path.join(item_path, sub, "mingw64", "bin", "g++.exe")
                    if os.path.exists(candidate2):
                        return candidate2
                    candidate3 = os.path.join(item_path, sub, "mingw32", "bin", "g++.exe")
                    if os.path.exists(candidate3):
                        return candidate3
    
    return None

def compile(gpp, out_name):
    """编译 DLL"""
    cmd = [
        gpp,
        "-shared", "-O2",
        "-o", os.path.join(BASE, out_name),
        os.path.join(BASE, "focus_hook.cpp"),
    ] + glob.glob(os.path.join(BASE, "minhook", "src", "**", "*.c"), recursive=True) + [
        "-I" + os.path.join(BASE, "minhook", "include"),
        "-luser32",
        "-static-libgcc",
    ]
    
    print(f"[*] 编译 {out_name}...")
    print(f"    命令: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"[ERR] 编译失败:\n{result.stderr}")
        return False
    
    if result.stderr:
        print(f"[WARN] 警告:\n{result.stderr}")
    
    print(f"[OK] {out_name} 编译成功")
    return True

def main():
    print("=== Focus Hook DLL 自动编译 ===\n")
    
    gpp = find_gpp()
    if not gpp:
        print("[ERR] 找不到 g++.exe")
        print("\n可能的原因:")
        print("  1. MinGW 不在 PATH 里，且不在常见安装位置")
        print("  2. 安装的是纯 C 编译器，没有 g++")
        print("\n解决方法:")
        print("  方法A: 把 MinGW 的 bin 目录加到系统 PATH，重启终端")
        print("  方法B: 在下面的 COMMON_PATHS 里添加你的 g++.exe 路径，重新运行")
        print("  方法C: 直接把 g++.exe 的完整路径告诉我，我帮你写死编译命令")
        input("\n按回车退出...")
        sys.exit(1)
    
    print(f"[OK] 找到编译器: {gpp}\n")
    
    # 判断编译器位数，优先编译对应版本
    # 简单策略：先编译当前编译器能编译的版本
    # 64位 mingw 一般只能编译 64 位，32位只能编译 32 位
    # 但 mingw-w64 的 x86_64 版本通常带 multilib，可以编 32 位（加 -m32）
    
    compiled = []
    
    # 尝试编译 64 位
    if compile(gpp, "focus_hook_x64.dll"):
        compiled.append("focus_hook_x64.dll")
    
    # 尝试编译 32 位（加 -m32）
    # 注意：需要 32 位运行时库，不一定成功
    gpp_dir = os.path.dirname(gpp)
    gpp32 = os.path.join(os.path.dirname(gpp_dir), "mingw32", "bin", "g++.exe")
    if os.path.exists(gpp32):
        if compile(gpp32, "focus_hook_x86.dll"):
            compiled.append("focus_hook_x86.dll")
    else:
        # 尝试用 -m32
        print("[*] 尝试用 -m32 编译 32 位版本...")
        cmd = [
            gpp, "-m32",
            "-shared", "-O2",
            "-o", os.path.join(BASE, "focus_hook_x86.dll"),
            os.path.join(BASE, "focus_hook.cpp"),
        ] + glob.glob(os.path.join(BASE, "minhook", "src", "**", "*.c"), recursive=True) + [
            "-I" + os.path.join(BASE, "minhook", "include"),
            "-luser32",
            "-static-libgcc",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print("[OK] focus_hook_x86.dll 编译成功")
            compiled.append("focus_hook_x86.dll")
        else:
            print(f"[WARN] -m32 编译 32 位失败（缺少 32 位库）:\n{result.stderr.strip()[:200]}")
    
    print(f"\n=== 结果 ===")
    if compiled:
        for f in compiled:
            print(f"  [OK] {f}")
        print(f"\n使用方式:")
        print(f"  python inject.py --game Game.exe")
    else:
        print("  [ERR] 全部编译失败")
    
    input("\n按回车退出...")

if __name__ == "__main__":
    main()
