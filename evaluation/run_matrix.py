#!/usr/bin/env python3
"""run_matrix - 方向5 全量矩阵跑批驱动（每档独立子进程，避免 llama_cpp 卸载不干净）"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = os.path.join(ROOT, '.venv', 'Scripts', 'python.exe')

# (label, gguf 文件, testsets, limit)
# FP16 在 6GB 卡上实测 ~10s/条（显存临界），全量不可行，仅跑 basic 前 60 条作参考；
# McNemar 对比时按 id 交集自动对齐，不受 limit 影响
RUNS = [
    ('v5-FP16',   'phi2-fp16.gguf',                  ('basic',), 60),
    ('v5-Q8_0',   'phi2-v5-q8_0.gguf',               ('basic', 'phase'), 0),
    ('v5-Q6_K',   'phi2-v5-q6_k.gguf',               ('basic', 'phase'), 0),
    ('v5-Q5_K_M', 'phi2-phased-v5-q5_k_m.gguf',      ('basic', 'phase'), 0),
    ('v5-Q4_K_M', 'phi2-v5-q4_k_m.gguf',             ('basic', 'phase'), 0),
    # 第一代 dmpc（8/1 遗留权重，非 8 月矩阵最终版）参考点：只跑 basic
    ('dmpc1-Q6_K', 'dmpc-q6_k.gguf',                 ('basic',), 0),
]

for label, model, testsets, limit in RUNS:
    for ts in testsets:
        print(f'\n===== {label} · {ts} =====', flush=True)
        cmd = [PY, os.path.join(HERE, 'eval_run.py'),
               '--model', os.path.join(ROOT, model),
               '--label', label, '--testset', ts]
        if limit:
            cmd += ['--limit', str(limit)]
        r = subprocess.run(cmd, cwd=ROOT)
        if r.returncode != 0:
            print(f'[警告] {label}/{ts} 退出码 {r.returncode}（继续下一档）', flush=True)
print('\n全部完成')
