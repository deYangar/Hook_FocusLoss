# 自动检测编译器并编译 focus_hook DLL（32位 + 64位）
$ErrorActionPreference = "Stop"
$base = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }

Write-Host "=== Focus Hook DLL 自动编译 ===" -ForegroundColor Cyan
Write-Host ""

# ── 1. 尝试找 cl.exe (Visual Studio) ──
function Find-VS {
    $vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    if (Test-Path $vswhere) {
        $installPath = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
        if ($installPath) {
            $vcvars = Join-Path $installPath "VC\Auxiliary\Build\vcvarsall.bat"
            if (Test-Path $vcvars) { return $vcvars }
        }
    }
    # fallback: 扫描常见路径
    $candidates = @(
        "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat",
        "C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvarsall.bat",
        "C:\Program Files\Microsoft Visual Studio\2022\Enterprise\VC\Auxiliary\Build\vcvarsall.bat",
        "C:\Program Files (x86)\Microsoft Visual Studio\2019\Community\VC\Auxiliary\Build\vcvarsall.bat",
        "C:\Program Files (x86)\Microsoft Visual Studio\2019\Professional\VC\Auxiliary\Build\vcvarsall.bat"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { return $c }
    }
    return $null
}

# ── 2. 尝试找 g++ (MinGW) ──
function Find-GCC {
    # 常见位置
    $candidates = @(
        "C:\mingw64\bin\g++.exe",
        "C:\mingw32\bin\g++.exe",
        "C:\msys64\mingw64\bin\g++.exe",
        "C:\msys64\mingw32\bin\g++.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { return $c }
    }
    # PATH 中
    try {
        $gpp = Get-Command g++ -ErrorAction Stop
        return $gpp.Source
    } catch { return $null }
}

$vcvars = Find-VS
$gpp = Find-GCC

if ($vcvars) {
    Write-Host "[*] 找到 Visual Studio: $vcvars" -ForegroundColor Green
    
    # 编译 64 位
    Write-Host "[*] 编译 64 位 DLL..."
    $cmd = "`"$vcvars`" x64 && cd /d `"$base`" && cl /LD focus_hook.cpp minhook\src\*.c /Iminhook\include /link user32.lib /OUT:focus_hook_x64.dll"
    cmd /c $cmd
    
    # 编译 32 位
    Write-Host "[*] 编译 32 位 DLL..."
    $cmd = "`"$vcvars`" x86 && cd /d `"$base`" && cl /LD focus_hook.cpp minhook\src\*.c /Iminhook\include /link user32.lib /OUT:focus_hook_x86.dll"
    cmd /c $cmd
}
elseif ($gpp) {
    Write-Host "[*] 找到 GCC: $gpp" -ForegroundColor Green
    
    # 判断是 64 位还是 32 位 gcc
    $is64 = & $gpp --version 2>$null
    $gccDir = Split-Path (Split-Path $gpp)
    
    # 尝试找对应位数的编译器
    $gcc64 = Join-Path $gccDir "bin\g++.exe"
    $gcc32 = Join-Path (Split-Path $gccDir) "mingw32\bin\g++.exe"
    
    if (Test-Path $gcc64) {
        Write-Host "[*] 编译 64 位 DLL..."
        & $gcc64 -shared -O2 -o "$base\focus_hook_x64.dll" `
            "$base\focus_hook.cpp" "$base\minhook\src\*.c" `
            -I"$base\minhook\include" -luser32 -static-libgcc
    }
    if (Test-Path $gcc32) {
        Write-Host "[*] 编译 32 位 DLL..."
        & $gcc32 -shared -O2 -o "$base\focus_hook_x86.dll" `
            "$base\focus_hook.cpp" "$base\minhook\src\*.c" `
            -I"$base\minhook\include" -luser32 -static-libgcc
    }
    if (-not (Test-Path $gcc64) -and -not (Test-Path $gcc32)) {
        # 只有一套编译器，先编译当前位数
        Write-Host "[!] 只找到一套 GCC，先编译当前位数版本..."
        $outName = if ($gpp -match "x64|mingw64|64") { "focus_hook_x64.dll" } else { "focus_hook_x86.dll" }
        & $gpp -shared -O2 -o "$base\$outName" `
            "$base\focus_hook.cpp" "$base\minhook\src\*.c" `
            -I"$base\minhook\include" -luser32 -static-libgcc
        Write-Host "[!] 另一个位数的 DLL 需要额外安装对应版本的 MinGW" -ForegroundColor Yellow
    }
}
else {
    Write-Host "[ERR] 未找到 C++ 编译器！" -ForegroundColor Red
    Write-Host ""
    Write-Host "请安装以下任一编译器：" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "方案 A - Visual Studio Build Tools（推荐）：" -ForegroundColor Cyan
    Write-Host "  1. 下载 https://aka.ms/vs/17/release/vs_BuildTools.exe"
    Write-Host "  2. 勾选 [C++ 桌面开发] 工作负载，安装"
    Write-Host ""
    Write-Host "方案 B - MinGW-w64（绿色版，无需安装）：" -ForegroundColor Cyan
    Write-Host "  1. 下载 https://github.com/brechtsanders/winlibs_mingw/releases"
    Write-Host "  2. 解压 mingw64 到 C:\mingw64，mingw32 到 C:\mingw32"
    Write-Host "  3. 或者把 bin 目录加到 PATH"
    Write-Host ""
    Write-Host "方案 C - 直接下载预编译 DLL（如果你信任我）：" -ForegroundColor Cyan
    Write-Host "  告诉我，我可以把编译好的 DLL 发给你"
    exit 1
}

# ── 检查结果 ──
Write-Host ""
$has64 = Test-Path "$base\focus_hook_x64.dll"
$has32 = Test-Path "$base\focus_hook_x86.dll"

if ($has64) { Write-Host "[OK] focus_hook_x64.dll 编译成功" -ForegroundColor Green }
if ($has32) { Write-Host "[OK] focus_hook_x86.dll 编译成功" -ForegroundColor Green }

if (-not $has64 -and -not $has32) {
    Write-Host "[ERR] 编译失败，请检查上方错误信息" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "编译完成！使用方式：" -ForegroundColor Cyan
Write-Host "  python inject.py --game Game.exe" -ForegroundColor White
