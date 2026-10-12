# v5-Q5_K_M · phase 评测汇总

- 模型: `phi2-phased-v5-q5_k_m.gguf` | n=200 | 2026-09-07 08:51:42
- 显存(加载后总量): 3102MB | 耗时 132.4s

## 总体

- 主指标（basic=精确匹配 / phase=规则容差）：**105/200 (52.5%, CI [45.6, 59.3])**
- 次级（指令主体 mode+uav_ids）：193/200 (96.5%, CI [93.0, 98.3])
- JSON 解析失败: 0/200
- 延迟 ms: mean=662 p50=621 max=2215

## 按 split

| split | n | 主指标 |
|---|---|---|
| seen | 56 | 41/56 (73.2%, CI [60.4, 83.0]) |
| in-range-unseen | 40 | 21/40 (52.5%, CI [37.5, 67.1]) |
| ood | 64 | 43/64 (67.2%, CI [55.0, 77.4]) |
| in | 40 | 0/40 (0.0%, CI [0.0, 8.8]) |

## 按类别

| category | n | 主指标 | subject_ok |
|---|---|---|---|
| ASSEMBLE | 40 | 37/40 (92.5%, CI [80.1, 97.4]) | 40/40 |
| HOLD | 40 | 40/40 (100.0%, CI [91.2, 100.0]) | 38/40 |
| OBSTACLE_AVOID | 40 | 18/40 (45.0%, CI [30.7, 60.2]) | 39/40 |
| RECON | 40 | 10/40 (25.0%, CI [14.2, 40.2]) | 38/40 |
| RECONFIGURE | 40 | 0/40 (0.0%, CI [0.0, 8.8]) | 38/40 |

## 失败样例（前 10 / 共 95）

- **P-003** [ASSEMBLE/ood] target-z: `All units, change formation.`
  - 期望 target=[-30.0, 8.0, 5.0]；输出 `{"mode": "swarm", "formation": "wedge", "uav_ids": [1, 2, 3, 4], "target": [-30.0, 8.0, 15.0]}`
- **P-008** [OBSTACLE_AVOID/seen] target-z: `UAV 3 and 4, adjust formation.`
  - 期望 target=[20.0, 0.0, 15.0]；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [3, 4], "target": [20.0, 0.0, 5.0]}`
- **P-009** [RECON/in-range-unseen] target-z: `All units, execute.`
  - 期望 target=[142.0, 171.0, 15.0]；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [142.0, 171.0, 5.0]}`
- **P-018** [RECON/seen] target-z: `Everyone, hold.`
  - 期望 target=[200.0, 150.0, 15.0]；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [200.0, 150.0, 5.0]}`
- **P-022** [RECONFIGURE/in] target-y: `Squad, take cover.`
  - 期望 target=[15.0, 15.0, 8.0]；输出 `{"mode": "swarm", "formation": "column", "uav_ids": [1, 2, 3, 4], "target": [15.0, -15.0, 15.0]}`
- **P-024** [RECONFIGURE/in] target-z: `All units, form up.`
  - 期望 target=[15.0, 15.0, 8.0]；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [15.0, 15.0, 15.0]}`
- **P-025** [OBSTACLE_AVOID/ood] target-z: `UAV 1 and 4, adjust formation.`
  - 期望 target=[-10.0, 0.0, 15.0]；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 4], "target": [-10.0, 0.0, 10.0]}`
- **P-026** [RECONFIGURE/in] target-y: `All units, evade.`
  - 期望 target=[15.0, 15.0, 8.0]；输出 `{"mode": "swarm", "formation": "wedge", "uav_ids": [1, 2, 3, 4], "target": [15.0, -15.0, 15.0]}`
- **P-027** [RECON/seen] target-z: `UAV 2 and 3, adjust formation.`
  - 期望 target=[168.0, 195.0, 15.0]；输出 `{"mode": "swarm", "formation": "wedge", "uav_ids": [2, 3], "target": [168.0, 195.0, 5.0]}`
- **P-029** [OBSTACLE_AVOID/ood] target-x: `UAV 2, change position.`
  - 期望 target=[-60.0, 0.0, 15.0]；输出 `{"mode": "single-agent", "formation": "free", "uav_ids": [2], "target": [-15.0, 0.0, 15.0]}`

