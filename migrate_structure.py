#!/usr/bin/env python3
"""migrate_structure.py - 一次性目录结构迁移脚本
将散乱文件迁移到规范化目录结构中。执行完毕后删除本脚本。
"""
import shutil
from pathlib import Path

ROOT = Path(__file__).parent
S = ROOT / 'scripts'

MOVES = [
    # (源, 目标)
    # 共享库 → src/common/
    (S / 'phase_rules.py',                   ROOT / 'src/common/phase_rules.py'),
    (S / 'phase_link.py',                    ROOT / 'src/common/phase_link.py'),
    (ROOT / 'safety/safety_layer.py',        ROOT / 'src/common/safety_layer.py'),
    (S / 'safety_layer_adversarial.py',      ROOT / 'src/common/safety_adversarial.py'),
    # 端侧节点 → src/nodes/edge/
    (S / 'nl_command_node_p04.py',           ROOT / 'src/nodes/edge/nl_command_node.py'),
    # 云端节点 → src/nodes/cloud/
    (S / 'cloud_phase_generator.py',         ROOT / 'src/nodes/cloud/phase_generator.py'),
    (S / 'adversarial_phase_generator.py',   ROOT / 'src/nodes/cloud/phase_generator_adv.py'),
    (S / 'cloud_heartbeat_node.py',          ROOT / 'src/nodes/cloud/heartbeat_node.py'),
    # 裁判 → src/nodes/referee/
    (S / 'referee_node.py',                  ROOT / 'src/nodes/referee/referee_node.py'),
    # 工具 → src/nodes/tools/
    (S / 'phase_fault_proxy.py',             ROOT / 'src/nodes/tools/fault_proxy.py'),
    (S / 'phase_consistency_eval.py',        ROOT / 'src/nodes/tools/phase_consistency.py'),
    # 训练 → src/training/
    (ROOT / 'train_phi2_qlora.py',           ROOT / 'src/training/train_qlora.py'),
    (ROOT / 'train_phi2_v6lc.py',            ROOT / 'src/training/train_qlora_v6lc.py'),
    (ROOT / 'merge_and_quantize.py',         ROOT / 'src/training/merge_and_quantize.py'),
    (ROOT / 'merge_v6lc.py',                 ROOT / 'src/training/merge_v6lc.py'),
    (ROOT / 'download_model.py',             ROOT / 'src/training/download_model.py'),
    (ROOT / 'setup_cuda_inference.py',       ROOT / 'src/training/setup_cuda_inference.py'),
    # 评测 → src/evaluation/
    (ROOT / 'evaluation/eval_run_v2.py',     ROOT / 'src/evaluation/eval_run.py'),
    (ROOT / 'evaluation/run_matrix_v2.py',   ROOT / 'src/evaluation/run_matrix.py'),
    (ROOT / 'evaluation/isolation_check.py', ROOT / 'src/evaluation/isolation_check.py'),
    (ROOT / 'evaluation/matrix_stability_check.py', ROOT / 'src/evaluation/matrix_stability_check.py'),
    (ROOT / 'evaluation/gen_testset_v2.py',  ROOT / 'src/evaluation/gen_testset.py'),
    (ROOT / 'evaluation/gen_causal.py',      ROOT / 'src/evaluation/gen_causal.py'),
    (ROOT / 'evaluation/gen_g7_trainset.py', ROOT / 'src/evaluation/gen_g7_trainset.py'),
    (ROOT / 'evaluation/p0_deep_dive.py',    ROOT / 'src/evaluation/p0_deep_dive.py'),
    (ROOT / 'evaluation/run_comm_pilot.py',  ROOT / 'src/evaluation/run_comm_pilot.py'),
    # 配置 → configs/
    (S / 'fi_disconnect.json',               ROOT / 'configs/fault_injection/fi_disconnect_10s.json'),
    (S / 'fi_replay.json',                   ROOT / 'configs/fault_injection/fi_replay_8s.json'),
    (S / 'settings_two_drones.json',         ROOT / 'configs/airsim/airsim_2v2.json'),
    (S / 'situations_testset.json',          ROOT / 'configs/scenarios/situations_testset.json'),
    # 启动脚本 → launch/
    (S / 'run_4drones.sh',                   ROOT / 'launch/launch_4uav_adversarial.sh'),
    (S / 'run_p04.sh',                      ROOT / 'launch/launch_1uav.sh'),
    (S / 'deploy_p04.sh',                    ROOT / 'launch/deploy_to_wsl.sh'),
    # 归档 → archive/
    (S / 'demo_degradation.sh',              ROOT / 'archive/legacy_scripts/'),
    (S / 'demo_full_chain.sh',               ROOT / 'archive/legacy_scripts/'),
    (S / 'run_demo.sh',                      ROOT / 'archive/legacy_scripts/'),
    (S / 'run_two_drones.sh',                ROOT / 'archive/legacy_scripts/'),
    (S / 'run_two_drones_v2.sh',             ROOT / 'archive/legacy_scripts/'),
    (S / 'wsl_deploy_llm.sh',                ROOT / 'archive/legacy_scripts/'),
    (S / 'wsl_eval_llm.sh',                  ROOT / 'archive/legacy_scripts/'),
    (S / 'wsl_llm_live_test.sh',             ROOT / 'archive/legacy_scripts/'),
    (S / 'wsl_regression_llm.sh',            ROOT / 'archive/legacy_scripts/'),
    (S / 'send_nl.py',                       ROOT / 'archive/legacy_scripts/'),
    (S / 'nl_command_node.py',               ROOT / 'archive/legacy_scripts/'),
    (S / 'p04_step3.sh',                     ROOT / 'archive/legacy_scripts/'),
    # 基准/验证 → src/evaluation/（保留在源码评测目录）
    (ROOT / 'benchmark.py',                  ROOT / 'src/evaluation/benchmark.py'),
    (ROOT / 'benchmark_gguf.py',             ROOT / 'src/evaluation/benchmark_gguf.py'),
    (ROOT / 'benchmark_matrix.py',           ROOT / 'src/evaluation/benchmark_matrix.py'),
    (ROOT / 'phase_verify.py',               ROOT / 'src/evaluation/phase_verify.py'),
    (ROOT / 'phase_verify_v3.py',            ROOT / 'src/evaluation/phase_verify_v3.py'),
    (ROOT / 'phase_verify_v4.py',            ROOT / 'src/evaluation/phase_verify_v4.py'),
    (ROOT / 'context_compression_test.py',   ROOT / 'src/evaluation/context_compression.py'),
    # eval_out 归档
    # logs 归档
]

# __init__.py 文件
INIT_FILES = [
    'src/common/__init__.py',
    'src/nodes/__init__.py',
    'src/nodes/edge/__init__.py',
    'src/nodes/cloud/__init__.py',
    'src/nodes/referee/__init__.py',
    'src/nodes/tools/__init__.py',
    'src/training/__init__.py',
    'src/evaluation/__init__.py',
]


def main():
    ok, skip, fail = 0, 0, 0
    for src, dst in MOVES:
        try:
            if not src.exists():
                print(f'  SKIP (不存在): {src.name}')
                skip += 1
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                print(f'  SKIP (已存在): {dst.name}')
                skip += 1
                continue
            shutil.copy2(str(src), str(dst))
            print(f'  OK: {src.name} -> {dst.relative_to(ROOT)}')
            ok += 1
        except Exception as e:
            print(f'  FAIL: {src.name} -> {e}')
            fail += 1

    for init in INIT_FILES:
        p = ROOT / init
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.touch()
            print(f'  INIT: {init}')

    print(f'\n=== 迁移完成: {ok} 成功, {skip} 跳过, {fail} 失败 ===')


if __name__ == '__main__':
    main()
