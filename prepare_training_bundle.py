#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prepare_training_bundle.py — 组装可拷往 Linux 的 3D 训练包。

做四件事：
1. 把 src/training/experiment_core_3d.py 复制到 training_3d_bundle/
2. 导出 BASE_CFG 为 config_reference_3d.json
3. 把所有文本文件统一为 LF（避免 Linux 下 bash 解释器报 \r 错误）
4. 生成 SHA256SUMS.txt 与 training_3d_bundle.zip（.sh 带可执行权限）
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src" / "training" / "experiment_core_3d.py"
BUNDLE = ROOT / "training_3d_bundle"
ZIP_PATH = ROOT / "training_3d_bundle.zip"

TEXT_SUFFIXES = {".py", ".sh", ".md", ".txt", ".json"}


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("experiment_core_3d_bundle", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["experiment_core_3d_bundle"] = module
    spec.loader.exec_module(module)
    return module


def normalize_lf(path: Path) -> None:
    raw = path.read_bytes()
    fixed = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    if fixed != raw:
        path.write_bytes(fixed)
        print(f"  LF normalized: {path.name}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    if not SRC.exists():
        raise FileNotFoundError(SRC)
    BUNDLE.mkdir(parents=True, exist_ok=True)

    dst = BUNDLE / "experiment_core_3d.py"
    dst.write_bytes(SRC.read_bytes())
    print(f"Copied: {SRC.relative_to(ROOT)} -> {dst.relative_to(ROOT)}")

    module = load_module(dst)
    config = dict(module.BASE_CFG)
    config_path = BUNDLE / "config_reference_3d.json"
    config_path.write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Config exported: {config_path.name} ({len(config)} keys)")

    for path in sorted(BUNDLE.iterdir()):
        if path.is_file() and path.suffix in TEXT_SUFFIXES:
            normalize_lf(path)

    manifest_path = BUNDLE / "SHA256SUMS.txt"
    entries = [
        f"{sha256(path)}  {path.name}"
        for path in sorted(BUNDLE.iterdir())
        if path.is_file() and path.name != manifest_path.name
    ]
    manifest_path.write_bytes(("\n".join(entries) + "\n").encode("utf-8"))
    print(f"Manifest written: {manifest_path.name} ({len(entries)} files)")

    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(BUNDLE.iterdir()):
            if not path.is_file():
                continue
            info = zipfile.ZipInfo(f"training_3d_bundle/{path.name}")
            mode = 0o755 if path.suffix == ".sh" else 0o644
            info.external_attr = mode << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    print(f"Zip written: {ZIP_PATH.name} ({ZIP_PATH.stat().st_size / 1024:.1f} KiB)")

    print("\nBundle contents:")
    for path in sorted(BUNDLE.iterdir()):
        if path.is_file():
            print(f"  {path.name:<32} {path.stat().st_size:>8} bytes")


if __name__ == "__main__":
    main()
