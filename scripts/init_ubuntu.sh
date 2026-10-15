#!/bin/bash
# init_ubuntu.sh - 实验室 Ubuntu 主机一键初始化
# 用法：将 phi2-training-migrate.tar.gz 和本脚本放到 home 目录，执行：
#   bash init_ubuntu.sh
set -e

echo "=========================================="
echo "  Phi-2 训练环境初始化（Ubuntu）"
echo "=========================================="

# 1. 解压迁移包
echo "[1/6] 解压迁移包..."
mkdir -p ~/phi2-training && cd ~/phi2-training
if [ -f ~/phi2-training-migrate.tar.gz ]; then
    tar xzf ~/phi2-training-migrate.tar.gz
    echo "    解压完成: $(find . -type f | wc -l) 个文件"
else
    echo "    错误：未找到 ~/phi2-training-migrate.tar.gz"
    echo "    请将迁移包放到 home 目录后重新运行"
    exit 1
fi

find . -name "*.sh" -exec dos2unix {} \; 2>/dev/null || true

# 2. 创建虚拟环境
echo "[2/6] 创建 Python 虚拟环境..."
if command -v conda &> /dev/null; then
    echo "    检测到 conda，创建环境 phi2..."
    conda create -n phi2 python=3.11 -y 2>/dev/null || true
    eval "$(conda shell.bash hook)"
    conda activate phi2
    PIP="pip"
    PYTHON="python"
else
    echo "    使用 venv..."
    python3 -m venv .venv
    source .venv/bin/activate
    PIP="pip"
    PYTHON="python3"
fi

# 3. 安装 CUDA 版 torch
echo "[3/6] 安装 CUDA 版 torch..."
CUDA_VER=$(nvidia-smi 2>/dev/null | grep -oP 'CUDA Version: \K[\d.]+')
echo "    CUDA 版本: ${CUDA_VER:-未知}"

if [[ "$CUDA_VER" == 12.* ]]; then
    $PIP install torch --index-url https://download.pytorch.org/whl/cu121 -q
elif [[ "$CUDA_VER" == 11.* ]]; then
    $PIP install torch --index-url https://download.pytorch.org/whl/cu118 -q
else
    echo "    警告：未检测到 CUDA，装默认 torch"
    $PIP install torch -q
fi

# 4. 安装其余依赖
echo "[4/6] 安装项目依赖..."
$PIP install -r requirements.txt -q

# 5. 下载基座模型
echo "[5/6] 检查基座模型..."
if [ ! -f "models/phi-2/config.json" ]; then
    echo "    基座不存在，开始下载（~5.2GB）..."
    $PYTHON download_model.py
else
    echo "    基座已存在，跳过"
fi

# 6. 验证
echo "[6/6] 验证..."
$PYTHON -c "
import torch
assert torch.cuda.is_available(), 'CUDA 不可用！检查驱动和 torch 版本'
print('  [OK] GPU:', torch.cuda.get_device_name(0))
print('  [OK] CUDA:', torch.version.cuda)
"
$PYTHON -c "
from transformers import AutoTokenizer
t = AutoTokenizer.from_pretrained('models/phi-2', trust_remote_code=True)
print(f'  [OK] Tokenizer vocab={t.vocab_size}')
" 2>/dev/null || echo "  [跳过] Tokenizer（模型未就绪）"
$PYTHON -c "
lines = open('datasets/dataset_phased_v5.jsonl').readlines()
print(f'  [OK] v5: {len(lines)} 条')
"
$PYTHON -c "
import os
print(f'  [OK] 测试集: {len(os.listdir(\"evaluation/testsets\"))} 个文件')
"

echo ""
echo "=========================================="
echo "  初始化完成！"
echo "=========================================="
echo ""
echo "  下一步："
echo "  1. 冒烟：sed -i 's/max_steps=400/max_steps=40/' train_phi2_qlora.py && python train_phi2_qlora.py"
echo "  2. 正式：sed -i 's/max_steps=40/max_steps=400/' train_phi2_qlora.py && python train_phi2_qlora.py"
echo "  3. 评测：python evaluation/run_matrix_v2.py"
echo "  文档：docs/训练迁移指南.md"
echo ""
