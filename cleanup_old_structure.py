#!/usr/bin/env python3
"""cleanup_old_structure.py - 清理旧目录结构中已被迁移到 src/ 的文件
执行 git rm（从 git 跟踪中移除）+ 磁盘删除（可选保留）
"""
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent

# 已迁移到新位置的旧文件（git rm + 磁盘删除）
OLD_TRACKED = [
    # 根目录 → src/training/
    'train_phi2_qlora.py',
    'train_phi2_v6lc.py',
    'merge_and_quantize.py',
    'merge_v6lc.py',
    'download_model.py',
    'setup_cuda_inference.py',
    # 根目录 → src/evaluation/
    'benchmark.py',
    'benchmark_gguf.py',
    'benchmark_matrix.py',
    'phase_verify.py',
    'phase_verify_v3.py',
    'phase_verify_v4.py',
    'context_compression_test.py',
    # scripts/ → src/common/
    'scripts/phase_rules.py',
    'scripts/phase_link.py',
    'scripts/safety_layer_adversarial.py',
    # scripts/ → src/nodes/
    'scripts/nl_command_node_p04.py',
    'scripts/cloud_phase_generator.py',
    'scripts/adversarial_phase_generator.py',
    'scripts/cloud_heartbeat_node.py',
    'scripts/referee_node.py',
    'scripts/phase_fault_proxy.py',
    'scripts/phase_consistency_eval.py',
    'scripts/nl_command_node.py',
    # scripts/ → configs/
    'scripts/fi_disconnect.json',
    'scripts/fi_replay.json',
    'scripts/settings_two_drones.json',
    'scripts/situations_testset.json',
    # scripts/ → launch/
    'scripts/run_4drones.sh',
    'scripts/run_p04.sh',
    'scripts/deploy_p04.sh',
    # scripts/ → archive/
    'scripts/demo_degradation.sh',
    'scripts/demo_full_chain.sh',
    'scripts/run_demo.sh',
    'scripts/run_two_drones.sh',
    'scripts/run_two_drones_v2.sh',
    'scripts/wsl_deploy_llm.sh',
    'scripts/wsl_eval_llm.sh',
    'scripts/wsl_llm_live_test.sh',
    'scripts/wsl_regression_llm.sh',
    'scripts/send_nl.py',
    'scripts/p04_step3.sh',
    'scripts/init_ubuntu.sh',
    # evaluation/ → src/evaluation/（旧文件仍跟踪）
    'evaluation/eval_run_v2.py',
    'evaluation/run_matrix_v2.py',
    'evaluation/isolation_check.py',
    'evaluation/matrix_stability_check.py',
    'evaluation/gen_testset_v2.py',
    'evaluation/gen_causal.py',
    'evaluation/gen_g7_trainset.py',
    'evaluation/p0_deep_dive.py',
    'evaluation/run_comm_pilot.py',
    # safety/ → src/common/
    'safety/safety_layer.py',
    'safety/validate_on_corpus.py',
]

# 旧目录中保留的文件（不删，但目录可能变空）
KEEP_IN_OLD = {
    'evaluation/': ['testsets/'],  # 冻结测试集保留在原位（评测脚本已引用该路径）
}

# 需要加入 .gitignore 的（存在磁盘上但不应入库）
GITIGNORE_ADD = """
# 模型权重与 GGUF 产物（可由 adapter+基座重建）
*.gguf
phi2-*-merged/
phi2-*-3060/
phi2-*-adapter/
models/

# 训练/评测中间产物
benchmark_run.log
benchmark_matrix_results.csv
context_compression_results.json
train_peak_vram.txt
__pycache__/
*.pyc

# 散落文献（已归档到 docs/文献精读2026/）
dt_paper.pdf
lieq_paper.txt

# 迁移脚本（一次性工具，执行后删除）
migrate_structure.py
create_wsl_package.py

# Ollama 安装包
OllamaSetup.exe
"""


def git_rm(path):
    """git rm -q --cached + 磁盘删除"""
    full = ROOT / path
    # 从 git 跟踪移除
    r = subprocess.run(['git', 'rm', '-q', '--cached', str(path)],
                       capture_output=True, text=True, cwd=str(ROOT))
    git_ok = r.returncode == 0
    # 磁盘删除
    disk_ok = False
    if full.exists():
        try:
            full.unlink()
            disk_ok = True
        except OSError:
            pass
    return git_ok, disk_ok


def main():
    ok, skip, fail = 0, 0, 0
    for path in OLD_TRACKED:
        full = ROOT / path
        if not full.exists() and not subprocess.run(
                ['git', 'ls-files', '--error-unmatch', path],
                capture_output=True, cwd=str(ROOT)).returncode == 0:
            skip += 1
            continue
        git_ok, disk_ok = git_rm(path)
        status = 'OK' if git_ok else ('DISK-ONLY' if disk_ok else 'FAIL')
        print(f'  {status:10s} {path}')
        if git_ok or disk_ok:
            ok += 1
        else:
            fail += 1

    # 更新 .gitignore
    gi = ROOT / '.gitignore'
    existing = gi.read_text(encoding='utf-8') if gi.exists() else ''
    if '# v2.0 结构清理' not in existing:
        gi.write_text(existing + '\n# v2.0 结构清理\n' + GITIGNORE_ADD, encoding='utf-8')
        print('\n  .gitignore 已更新')

    # 删除空目录
    for d in ['safety', 'scripts/__pycache__', 'evaluation/__pycache__']:
        p = ROOT / d
        if p.exists() and not any(p.iterdir()):
            p.rmdir()
            print(f'  空目录已删: {d}')

    print(f'\n=== 清理完成: {ok} 移除, {skip} 跳过, {fail} 失败 ===')
    print('\n下一步：')
    print('  git add -A')
    print('  git commit -m "清理旧目录结构：删除已迁移到 src/ 的旧文件"')


if __name__ == '__main__':
    main()
