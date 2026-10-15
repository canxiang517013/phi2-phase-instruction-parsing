"""
pdl.py — 并行分块下载器（ModelScope 直链多线程加速）

用法:
    python3 scripts/pdl.py <URL> <输出文件> [线程数] [期望大小MB]

原理: 解析 302 得到 CDN 直链后，按 Range 分块多线程下载，
      绕过单连接限速。支持断点续跑（已完成分块跳过）。
仅依赖标准库。
"""
import os
import sys
import time
import urllib.request
import concurrent.futures as cf

CHUNK = 8 * 1024 * 1024  # 每个子请求 8MB


def resolve(url: str) -> str:
    """跟随重定向，返回最终直链。"""
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.url


def probe_size(url: str) -> int:
    req = urllib.request.Request(url, headers={"Range": "bytes=0-0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        if r.status != 206:
            raise RuntimeError(f"服务器不支持 Range 请求 (HTTP {r.status})，无法并行下载")
        cr = r.headers.get("Content-Range")  # bytes 0-0/TOTAL
        if cr:
            return int(cr.split("/")[-1])
        raise RuntimeError("响应缺少 Content-Range")


def fetch_range(final_url: str, start: int, end: int, out_path: str, offset: int):
    """下载 [start,end] 并写入 out_path 的 offset 处。
    中断后从块内已写位置续传，不重复已下载字节。"""
    pos = offset
    for attempt in range(12):
        try:
            req = urllib.request.Request(
                final_url, headers={"Range": f"bytes={start + (pos - offset)}-{end}"})
            with urllib.request.urlopen(req, timeout=60) as r, open(out_path, "r+b") as f:
                if r.status != 206:
                    raise RuntimeError(f"Range 请求被忽略 (HTTP {r.status})")
                while True:
                    buf = r.read(1024 * 1024)
                    if not buf:
                        break
                    f.seek(pos)
                    f.write(buf)
                    pos += len(buf)
            if pos - offset >= end - start + 1:
                return pos - offset
        except Exception as e:
            time.sleep(2 * min(attempt + 1, 5))
            print(f"  [retry {attempt+1}] {start//(1024*1024)}MB 块 "
                  f"从 {pos//(1024*1024)}MB 处续: {e}", flush=True)
    raise RuntimeError(f"分块 {start}-{end} 多次重试失败")


def main():
    url, out_path = sys.argv[1], sys.argv[2]
    workers = int(sys.argv[3]) if len(sys.argv) > 3 else 8
    expect_mb = float(sys.argv[4]) if len(sys.argv) > 4 else 0

    final_url, total = None, -1
    for attempt in range(6):
        try:
            final_url = resolve(url)
            total = probe_size(final_url)
            break
        except Exception as e:
            print(f"  [probe retry {attempt+1}] {e}", flush=True)
            time.sleep(3 * (attempt + 1))
    if not final_url or total <= 0:
        print("[pdl] ❌ 解析直链/探测大小失败", flush=True)
        sys.exit(1)
    print(f"[pdl] 总大小: {total/1024/1024:.1f} MB | 线程: {workers} | 直链已解析", flush=True)
    if expect_mb and abs(total / 1024 / 1024 - expect_mb) > 1:
        print(f"[pdl] ⚠️ 大小不符: 期望 {expect_mb}MB", flush=True)
        sys.exit(1)

    # 预分配文件 + 进度文件
    if not os.path.exists(out_path) or os.path.getsize(out_path) != total:
        with open(out_path, "wb") as f:
            f.truncate(total)
    prog_path = out_path + ".pdlprog"
    done = set()
    if os.path.exists(prog_path):
        done = set(int(x) for x in open(prog_path).read().split() if x)

    tasks = []
    with open(out_path, "r+b"):
        pass
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {}
        t0 = time.time()
        written = 0
        for s in range(0, total, CHUNK):
            e = min(s + CHUNK, total) - 1
            if s in done:
                written += e - s + 1
                continue
            futures[ex.submit(fetch_range, final_url, s, e, out_path, s)] = (s, e - s + 1)
        with open(prog_path, "a") as pf:
            for fu in cf.as_completed(futures):
                n = fu.result()
                s, sz = futures[fu]
                written += n
                pf.write(f"{s}\n")
                pf.flush()
                speed = written / 1024 / 1024 / max(time.time() - t0, 1)
                print(f"[pdl] {written/1024/1024:.0f}/{total/1024/1024:.0f} MB "
                      f"({100*written/total:.1f}%) {speed:.1f} MB/s", flush=True)
    os.remove(prog_path)
    print(f"[pdl] ✅ 完成: {out_path} ({total/1024/1024:.1f} MB)", flush=True)


if __name__ == "__main__":
    main()
