"""
fetch_deps.py — 从本地 torch wheel 的 METADATA 提取**精确钉版的大依赖**
（nvidia-* CUDA 库 + triton），用 pdl 并行下载到 wheels/ 目录。
小体积纯 Python 依赖不在此处理，由 pip 在线安装（量小）。

用法: python3 scripts/fetch_deps.py
"""
import os
import re
import subprocess
import sys
import time
import urllib.request
import zipfile

WHEELS = "/home/abc/桌面/syc/phi2-training/wheels"
ALIYUN = "https://mirrors.aliyun.com/pypi/simple"
TORCH_WHEEL = os.path.join(WHEELS, "torch-2.5.1+cu121-cp311-cp311-linux_x86_64.whl")
PDL = "/home/abc/桌面/syc/phi2-training/scripts/pdl.py"
# 只处理这些钉版大包（其余交给 pip 在线解析，避免自实现版本选择器）
WANT_PREFIXES = ("nvidia-", "triton")


def torch_reqs():
    with zipfile.ZipFile(TORCH_WHEEL) as z:
        meta_name = [n for n in z.namelist() if n.endswith(".dist-info/METADATA")][0]
        meta = z.read(meta_name).decode()
    out = []
    for line in meta.splitlines():
        if not line.startswith("Requires-Dist:") or "extra ==" in line:
            continue
        req = line[len("Requires-Dist:"):].strip()
        m = re.match(r"([A-Za-z0-9._-]+)\s*\((.*)\)$|^([A-Za-z0-9._-]+)\s*(.*)$", req)
        name = (m.group(1) or m.group(3)).strip()
        spec = (m.group(2) or m.group(4) or "").strip()
        if name.startswith(WANT_PREFIXES) and "==" in spec:
            ver = re.search(r"==\s*([0-9][A-Za-z0-9.+!]*)", spec).group(1)
            out.append((name, ver))
    return out


def wheel_ok(fn):
    if "aarch64" in fn or "win_" in fn or "macosx" in fn:
        return False
    if "x86_64" not in fn:
        return fn.endswith("py3-none-any.whl")
    if "manylinux" not in fn and "linux_x86_64" not in fn:
        return False
    return "cp311" in fn or "py3-none-" in fn or "py2.py3-" in fn


def fetch(url, tries=8):
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return r.read().decode()
        except Exception as e:
            last = e
            time.sleep(3 * min(i + 1, 5))
    raise RuntimeError(f"获取页面失败 {url}: {last}")


def pick_url(name, ver):
    norm = name.replace("_", "-").lower()
    html = fetch(f"{ALIYUN}/{norm}/")
    for href in re.findall(r'href="([^"]+)"', html):
        fn = href.rsplit("/", 1)[-1].split("#")[0]
        if not fn.endswith(".whl"):
            continue
        if f"-{ver}-" not in fn:
            continue
        if not wheel_ok(fn):
            continue
        url = href.split("#")[0]
        if url.startswith("../"):
            url = ALIYUN + "/" + url[3:]
        elif url.startswith("/"):
            url = "https://mirrors.aliyun.com" + url
        return fn, url
    return None


def main():
    reqs = torch_reqs()
    print("[deps] 需并行下载的钉版大依赖:")
    plan = []
    for name, ver in reqs:
        got = pick_url(name, ver)
        if got is None:
            print(f"[deps] ❌ 未找到: {name}=={ver}")
            sys.exit(1)
        fn, url = got
        plan.append((fn, url))
        print(f"[deps] {name}=={ver} → {fn}")

    for fn, url in plan:
        out = os.path.join(WHEELS, fn)
        # 有 .pdlprog 视为未完成；无则与远端大小比对
        need = True
        if os.path.exists(out) and not os.path.exists(out + ".pdlprog"):
            req_head = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req_head, timeout=30) as r:
                remote = int(r.headers.get("Content-Length", 0))
            if os.path.getsize(out) == remote:
                print(f"[deps] 已存在: {fn}")
                need = False
        if not need:
            continue
        for i in range(10):
            r = subprocess.run([sys.executable, PDL, url, out, "6"])
            if r.returncode == 0:
                break
            print(f"[deps] {fn} 第 {i+1} 次中断，续传...")
            time.sleep(2)
        else:
            print(f"[deps] ❌ 多次失败: {fn}")
            sys.exit(1)
    print("[deps] ✅ 大依赖 wheel 全部就绪")


if __name__ == "__main__":
    main()
