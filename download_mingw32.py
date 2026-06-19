import urllib.request
import ssl
import os
import zipfile

url = "https://github.com/brechtsanders/winlibs_mingw/releases/download/16.1.0posix-14.0.0-ucrt-r3/winlibs-i686-posix-dwarf-gcc-16.1.0-mingw-w64ucrt-14.0.0-r3.zip"
zip_path = os.path.join(os.environ.get("TEMP", "C:\\tmp"), "mingw32.zip")
dest = r"C:\Users\Yang\.openclaw\workspace\focus_hook\mingw32"

print("[*] 下载 32位 MinGW (~140MB)...")
print(f"    URL: {url}")

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def reporthook(block_num, block_size, total_size):
    downloaded = block_num * block_size
    if total_size > 0:
        pct = min(downloaded * 100 / total_size, 100)
        print(f"\r    进度: {pct:.1f}% ({downloaded//1024//1024}MB / {total_size//1024//1024}MB)", end="", flush=True)

urllib.request.urlretrieve(url, zip_path, reporthook)
print(f"\n[OK] 下载完成: {zip_path}")

print("[*] 解压...")
os.makedirs(dest, exist_ok=True)
with zipfile.ZipFile(zip_path, 'r') as z:
    z.extractall(dest)
print(f"[OK] 解压完成: {dest}")

# 找 mingw32 目录
dirs = [d for d in os.listdir(dest) if os.path.isdir(os.path.join(dest, d))]
if dirs and os.path.exists(os.path.join(dest, dirs[0], "bin", "g++.exe")):
    inner = os.path.join(dest, dirs[0])
    # 把内容移到顶层
    for item in os.listdir(inner):
        src = os.path.join(inner, item)
        dst = os.path.join(dest, item)
        if os.path.exists(dst):
            continue
        os.rename(src, dst)
    os.rmdir(inner)
    print("[OK] 目录整理完成")

gpp = os.path.join(dest, "bin", "g++.exe")
if os.path.exists(gpp):
    print(f"[OK] g++ 路径: {gpp}")
else:
    print(f"[ERR] 找不到 g++.exe")
