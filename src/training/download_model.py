"""
Step 0: 下载基座模型 microsoft/phi-2 到本地 ./models/phi-2

说明:
    本机的 huggingface.co 实测连接超时（无法直连），因此改用 ModelScope
    （魔搭社区，国内可达且速度快）下载 microsoft/phi-2 的官方镜像。

用法:
    python download_model.py

完成后会输出模型本地路径，训练脚本 (train_phi2_qlora.py) 将直接读取该路径。
"""
import os
import sys
import subprocess

MODEL_ID = "microsoft/phi-2"
LOCAL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "models", "phi-2")  # 仓库根/models/phi-2

# phi-2 完整文件清单，用于完整性校验（来源于 ModelScope 仓库）
EXPECTED_FILES = [
    "config.json",
    "generation_config.json",
    "model-00001-of-00002.safetensors",
    "model-00002-of-00002.safetensors",
    "model.safetensors.index.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.json",
    "merges.txt",
    "special_tokens_map.json",
    "added_tokens.json",
]


def ensure_modelscope():
    """确保 modelscope 已安装，未安装则自动 pip 安装。"""
    try:
        import modelscope  # noqa: F401
        return
    except ImportError:
        pass
    print("[download_model] 未检测到 modelscope，开始自动安装 ...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "modelscope"])
    print("[download_model] modelscope 安装完成。")


def is_complete():
    """检查本地模型是否已完整下载。"""
    if not os.path.isdir(LOCAL_DIR):
        return False
    for f in EXPECTED_FILES:
        p = os.path.join(LOCAL_DIR, f)
        if not os.path.exists(p) or os.path.getsize(p) == 0:
            return False
    return True


def main():
    # 1. 已存在则跳过
    if is_complete():
        print(f"[download_model] 模型已存在且完整，跳过下载:\n  {LOCAL_DIR}")
        return LOCAL_DIR

    # 2. 确保依赖
    ensure_modelscope()

    # 3. 下载
    from modelscope import snapshot_download

    os.makedirs(os.path.dirname(LOCAL_DIR), exist_ok=True)
    print(f"[download_model] 开始从 ModelScope 下载 {MODEL_ID} ...")
    print(f"[download_model] 目标目录: {LOCAL_DIR}")
    print("[download_model] 模型约 5.5GB，请耐心等待（视网速 3~15 分钟）...")
    path = snapshot_download(
        model_id=MODEL_ID,
        local_dir=LOCAL_DIR,
        revision="master",
    )
    print(f"[download_model] 下载完成: {path}")

    # 4. 完整性校验
    missing = [f for f in EXPECTED_FILES
               if not os.path.exists(os.path.join(LOCAL_DIR, f))]
    if missing:
        print(f"[download_model] ⚠️ 警告：以下文件缺失: {missing}")
        print("[download_model] 请删除整个目录后重新运行本脚本。")
        sys.exit(1)

    # 5. 统计大小
    total = 0
    for f in EXPECTED_FILES:
        total += os.path.getsize(os.path.join(LOCAL_DIR, f))
    print(f"[download_model] ✅ 校验通过，共 {len(EXPECTED_FILES)} 个文件，"
          f"合计 {total / 1024 / 1024:.1f} MB")
    print(f"[download_model] 本地路径: {LOCAL_DIR}")
    return LOCAL_DIR


if __name__ == "__main__":
    main()
