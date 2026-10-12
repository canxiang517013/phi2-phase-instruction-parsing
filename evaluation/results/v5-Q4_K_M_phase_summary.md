# v5-Q4_K_M · phase 评测汇总

- 模型: `phi2-v5-q4_k_m.gguf` | n=200 | 2026-09-07 08:56:04
- 显存(加载后总量): 2864MB | 耗时 119.3s

## 总体

- 主指标（basic=精确匹配 / phase=规则容差）：**86/200 (43.0%, CI [36.3, 49.9])**
- 次级（指令主体 mode+uav_ids）：190/200 (95.0%, CI [91.0, 97.3])
- JSON 解析失败: 0/200
- 延迟 ms: mean=597 p50=584 max=726

## 按 split

| split | n | 主指标 |
|---|---|---|
| seen | 56 | 36/56 (64.3%, CI [51.2, 75.5]) |
| in-range-unseen | 40 | 17/40 (42.5%, CI [28.5, 57.8]) |
| ood | 64 | 33/64 (51.6%, CI [39.6, 63.4]) |
| in | 40 | 0/40 (0.0%, CI [0.0, 8.8]) |

## 按类别

| category | n | 主指标 | subject_ok |
|---|---|---|---|
| ASSEMBLE | 40 | 17/40 (42.5%, CI [28.5, 57.8]) | 38/40 |
| HOLD | 40 | 40/40 (100.0%, CI [91.2, 100.0]) | 37/40 |
| OBSTACLE_AVOID | 40 | 10/40 (25.0%, CI [14.2, 40.2]) | 38/40 |
| RECON | 40 | 19/40 (47.5%, CI [32.9, 62.5]) | 39/40 |
| RECONFIGURE | 40 | 0/40 (0.0%, CI [0.0, 8.8]) | 38/40 |

## 失败样例（前 10 / 共 114）

- **P-001** [ASSEMBLE/in-range-unseen] target-z: `Everyone, scout ahead.`
  - 期望 target=[0.0, -10.0, 5.0]；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [0.0, -10.0, 15.0]}`
- **P-003** [ASSEMBLE/ood] target-z: `All units, change formation.`
  - 期望 target=[-30.0, 8.0, 5.0]；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [-30.0, 8.0, 15.0]}`
- **P-008** [OBSTACLE_AVOID/seen] target-z: `UAV 3 and 4, adjust formation.`
  - 期望 target=[20.0, 0.0, 15.0]；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [3, 4], "target": [20.0, 0.0, 20.0]}`
- **P-009** [RECON/in-range-unseen] target-z: `All units, execute.`
  - 期望 target=[142.0, 171.0, 15.0]；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [142.0, 171.0, 5.0]}`
- **P-010** [ASSEMBLE/ood] target-z: `UAV 2, proceed.`
  - 期望 target=[18.0, 0.0, 5.0]；输出 `{"mode": "single-agent", "formation": "free", "uav_ids": [2], "target": [18.0, 0.0, 15.0]}`
- **P-013** [ASSEMBLE/ood] target-z: `UAV 3, proceed.`
  - 期望 target=[25.0, 25.0, 5.0]；输出 `{"mode": "single-agent", "formation": "free", "uav_ids": [3], "target": [25.0, 25.0, 25.0]}`
- **P-021** [ASSEMBLE/in-range-unseen] target-z: `Squad, take cover.`
  - 期望 target=[0.0, 3.0, 5.0]；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3], "target": [0.0, 3.0, 15.0]}`
- **P-022** [RECONFIGURE/in] target-y: `Squad, take cover.`
  - 期望 target=[15.0, 15.0, 8.0]；输出 `{"mode": "swarm", "formation": "column", "uav_ids": [1, 2, 3, 4], "target": [15.0, -5.0, 15.0]}`
- **P-024** [RECONFIGURE/in] target-z: `All units, form up.`
  - 期望 target=[15.0, 15.0, 8.0]；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [15.0, 15.0, 15.0]}`
- **P-025** [OBSTACLE_AVOID/ood] target-z: `UAV 1 and 4, adjust formation.`
  - 期望 target=[-10.0, 0.0, 15.0]；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 4], "target": [-10.0, 0.0, 10.0]}`

