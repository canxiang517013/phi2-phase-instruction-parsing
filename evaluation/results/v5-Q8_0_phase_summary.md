# v5-Q8_0 · phase 评测汇总

- 模型: `phi2-v5-q8_0.gguf` | n=200 | 2026-09-07 08:40:52
- 显存(加载后总量): 3962MB | 耗时 153.1s

## 总体

- 主指标（basic=精确匹配 / phase=规则容差）：**115/200 (57.5%, CI [50.6, 64.1])**
- 次级（指令主体 mode+uav_ids）：172/200 (86.0%, CI [80.5, 90.1])
- JSON 解析失败: 0/200
- 延迟 ms: mean=765 p50=635 max=2189

## 按 split

| split | n | 主指标 |
|---|---|---|
| seen | 56 | 45/56 (80.4%, CI [68.2, 88.7]) |
| in-range-unseen | 40 | 23/40 (57.5%, CI [42.2, 71.5]) |
| ood | 64 | 47/64 (73.4%, CI [61.5, 82.7]) |
| in | 40 | 0/40 (0.0%, CI [0.0, 8.8]) |

## 按类别

| category | n | 主指标 | subject_ok |
|---|---|---|---|
| ASSEMBLE | 40 | 23/40 (57.5%, CI [42.2, 71.5]) | 37/40 |
| HOLD | 40 | 40/40 (100.0%, CI [91.2, 100.0]) | 33/40 |
| OBSTACLE_AVOID | 40 | 21/40 (52.5%, CI [37.5, 67.1]) | 36/40 |
| RECON | 40 | 31/40 (77.5%, CI [62.5, 87.7]) | 35/40 |
| RECONFIGURE | 40 | 0/40 (0.0%, CI [0.0, 8.8]) | 31/40 |

## 失败样例（前 10 / 共 85）

- **P-003** [ASSEMBLE/ood] target-z: `All units, change formation.`
  - 期望 target=[-30.0, 8.0, 5.0]；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [1, 2, 3, 4], "target": [-30.0, 8.0, 15.0]}`
- **P-008** [OBSTACLE_AVOID/seen] target-z: `UAV 3 and 4, adjust formation.`
  - 期望 target=[20.0, 0.0, 15.0]；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [3, 4], "target": [20.0, 0.0, 20.0]}`
- **P-009** [RECON/in-range-unseen] target-z: `All units, execute.`
  - 期望 target=[142.0, 171.0, 15.0]；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [142.0, 171.0, 5.0]}`
- **P-013** [ASSEMBLE/ood] target-z: `UAV 3, proceed.`
  - 期望 target=[25.0, 25.0, 5.0]；输出 `{"mode": "single-agent", "formation": "free", "uav_ids": [3], "target": [25.0, 25.0, 25.0]}`
- **P-021** [ASSEMBLE/in-range-unseen] target-z: `Squad, take cover.`
  - 期望 target=[0.0, 3.0, 5.0]；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3], "target": [0.0, 3.0, 15.0]}`
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

