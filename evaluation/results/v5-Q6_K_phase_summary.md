# v5-Q6_K · phase 评测汇总

- 模型: `phi2-v5-q6_k.gguf` | n=200 | 2026-09-07 08:46:49
- 显存(加载后总量): 3361MB | 耗时 165.4s

## 总体

- 主指标（basic=精确匹配 / phase=规则容差）：**108/200 (54.0%, CI [47.1, 60.8])**
- 次级（指令主体 mode+uav_ids）：185/200 (92.5%, CI [88.0, 95.4])
- JSON 解析失败: 0/200
- 延迟 ms: mean=827 p50=709 max=2712

## 按 split

| split | n | 主指标 |
|---|---|---|
| seen | 56 | 40/56 (71.4%, CI [58.5, 81.6]) |
| in-range-unseen | 40 | 21/40 (52.5%, CI [37.5, 67.1]) |
| ood | 64 | 47/64 (73.4%, CI [61.5, 82.7]) |
| in | 40 | 0/40 (0.0%, CI [0.0, 8.8]) |

## 按类别

| category | n | 主指标 | subject_ok |
|---|---|---|---|
| ASSEMBLE | 40 | 26/40 (65.0%, CI [49.5, 77.9]) | 39/40 |
| HOLD | 40 | 40/40 (100.0%, CI [91.2, 100.0]) | 39/40 |
| OBSTACLE_AVOID | 40 | 19/40 (47.5%, CI [32.9, 62.5]) | 37/40 |
| RECON | 40 | 23/40 (57.5%, CI [42.2, 71.5]) | 36/40 |
| RECONFIGURE | 40 | 0/40 (0.0%, CI [0.0, 8.8]) | 34/40 |

## 失败样例（前 10 / 共 92）

- **P-003** [ASSEMBLE/ood] target-z: `All units, change formation.`
  - 期望 target=[-30.0, 8.0, 5.0]；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [1, 2, 3, 4], "target": [-30.0, 8.0, 15.0]}`
- **P-008** [OBSTACLE_AVOID/seen] target-z: `UAV 3 and 4, adjust formation.`
  - 期望 target=[20.0, 0.0, 15.0]；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [3, 4], "target": [20.0, 0.0, 20.0]}`
- **P-009** [RECON/in-range-unseen] target-z: `All units, execute.`
  - 期望 target=[142.0, 171.0, 15.0]；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [1, 2, 3, 4], "target": [142.0, 171.0, 5.0]}`
- **P-013** [ASSEMBLE/ood] target-z: `UAV 3, proceed.`
  - 期望 target=[25.0, 25.0, 5.0]；输出 `{"mode": "single-agent", "formation": "free", "uav_ids": [3], "target": [25.0, 25.0, 25.0]}`
- **P-018** [RECON/seen] target-z: `Everyone, hold.`
  - 期望 target=[200.0, 150.0, 15.0]；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [200.0, 150.0, 5.0]}`
- **P-022** [RECONFIGURE/in] target-z: `Squad, take cover.`
  - 期望 target=[15.0, 15.0, 8.0]；输出 `{"mode": "swarm", "formation": "column", "uav_ids": [1, 2, 3, 4], "target": [15.0, 15.0, 15.0]}`
- **P-024** [RECONFIGURE/in] target-z: `All units, form up.`
  - 期望 target=[15.0, 15.0, 8.0]；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [15.0, 15.0, 15.0]}`
- **P-025** [OBSTACLE_AVOID/ood] target-z: `UAV 1 and 4, adjust formation.`
  - 期望 target=[-10.0, 0.0, 15.0]；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 4], "target": [-10.0, 0.0, 10.0]}`
- **P-026** [RECONFIGURE/in] target-z: `All units, evade.`
  - 期望 target=[15.0, 15.0, 8.0]；输出 `{"mode": "swarm", "formation": "wedge", "uav_ids": [1, 2, 3, 4], "target": [15.0, 15.0, 15.0]}`
- **P-030** [RECONFIGURE/in] target-z: `UAV 2, proceed.`
  - 期望 target=[15.0, 15.0, 8.0]；输出 `{"mode": "single-agent", "formation": "free", "uav_ids": [2], "target": [15.0, 15.0, 15.0]}`

