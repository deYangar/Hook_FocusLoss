# Focus Hook

Focus Hook 是一个 Windows 小工具，用于让部分单机游戏在失去前台焦点后仍然继续运行、播放声音或响应手柄输入。

项目包含：

- 注入器 GUI：`focus_hook_gui.py`
- Hook DLL 源码：`focus_hook.cpp`
- 32/64 位 DLL：`focus_hook_x86.dll`、`focus_hook_x64.dll`
- 便携版 GUI：`dist/FocusHook.exe`

> 实现参考了 [NoFocusLoss](https://github.com/araghon007/nofocusloss) 的核心思路：替换目标窗口 WndProc，拦截失焦消息，并 Hook `GetForegroundWindow` / `SetCursorPos`。

## 快速使用

### 方式 A：直接运行便携版

1. 先启动目标游戏。
2. 右键管理员运行：

```text
dist/FocusHook.exe
```

3. 在窗口列表中选择目标游戏窗口。
4. 点击 **Hook 开始**。
5. Alt+Tab 切出去测试游戏是否继续运行。
6. 需要恢复默认焦点行为时，点击 **Hook 停止**。

### 方式 B：从源码运行 GUI

```powershell
python focus_hook_gui.py
```

GUI 会自动申请管理员权限。

## GUI 功能

- 直接列出可见顶层窗口，而不是列全部进程。
- 支持按窗口标题 / 进程名搜索。
- 自动检测目标进程是 32 位还是 64 位。
- 自动注入对应 DLL：
  - 32 位目标：`focus_hook_x86.dll`
  - 64 位目标：`focus_hook_x64.dll`
- 支持即时卸载 Hook：
  - 枚举目标进程模块
  - 找到已加载的 `focus_hook_x86.dll` / `focus_hook_x64.dll`
  - 远程调用 `FreeLibrary`
  - 触发 DLL 的 `DLL_PROCESS_DETACH`
  - 恢复原始 WndProc，并禁用 MinHook

## Hook 原理

DLL 注入目标进程后，会定位当前进程内面积最大的窗口作为主窗口，然后：

### API Hook

| API | 行为 |
| --- | --- |
| `GetForegroundWindow()` | 返回目标游戏自己的窗口句柄 |
| `SetCursorPos(x, y)` | 目标失焦时阻止游戏继续强制移动鼠标 |

### 窗口消息拦截

替换目标窗口的 `WndProc` 后，会拦截以下失焦相关消息：

| 消息 | 行为 |
| --- | --- |
| `WM_NCACTIVATE` | 失焦时返回 0，阻断后续 deactivate 链路 |
| `WM_ACTIVATE` | 拦截 `WA_INACTIVE` |
| `WM_ACTIVATEAPP` | 拦截应用失活 |
| `WM_KILLFOCUS` | 拦截键盘焦点丢失 |
| `WM_IME_SETCONTEXT` | 拦截输入法上下文失活 |

## 编译 DLL

### 64 位 DLL

```powershell
python compile.py
```

当前环境会自动找到 64 位 MinGW 并生成：

```text
focus_hook_x64.dll
```

### 32 位 DLL

仓库内本地工具链 `mingw32/` 可用于编译 32 位 DLL：

```powershell
& ".\mingw32\bin\g++.exe" -shared -O2 -o focus_hook_x86.dll focus_hook.cpp minhook\src\buffer.c minhook\src\hook.c minhook\src\trampoline.c minhook\src\hde\hde32.c minhook\src\hde\hde64.c -Iminhook\include -luser32 -static-libgcc
```

## 打包 GUI

使用 PyInstaller 打包成单文件 EXE：

```powershell
pyinstaller --onefile --windowed --name "FocusHook" --add-data "focus_hook_x64.dll;." --add-data "focus_hook_x86.dll;." focus_hook_gui.py
```

产物：

```text
dist/FocusHook.exe
```

## 文件说明

| 文件 / 目录 | 说明 |
| --- | --- |
| `focus_hook.cpp` | C++ DLL 源码 |
| `focus_hook_gui.py` | Tkinter GUI 注入器，支持窗口列表、注入、卸载 |
| `focus_hook_x64.dll` | 64 位 DLL |
| `focus_hook_x86.dll` | 32 位 DLL |
| `dist/FocusHook.exe` | 便携版 GUI |
| `minhook/` | MinHook 源码依赖 |
| `inject.py` | 旧版命令行注入器，保留用于调试 |
| `compile.py` | DLL 编译辅助脚本 |

## 注意事项

- 需要管理员权限，否则可能无法打开目标进程或注入 DLL。
- 仅建议用于单机游戏或本地测试程序。
- 不要用于带反作弊的联网游戏。
- 如果 **Hook 停止** 失败，说明目标进程拒绝或阻止卸载；此时重启目标程序即可恢复。
- 某些游戏可能有多窗口或特殊渲染窗口，优先选择真实游戏窗口标题对应的那一项。
