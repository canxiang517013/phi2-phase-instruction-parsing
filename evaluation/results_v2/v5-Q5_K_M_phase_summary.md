# v5-Q5_K_M · phase 评测汇总（v2 六指标）

- 模型 `phi2-phased-v5-q5_k_m.gguf` | n=200 | 2026-10-12 21:48:01 | 显存 3764MB | 耗时 144.3s

## 六指标总览

- 主指标（按 judge 类型）：**101/200 (50.5%, CI [43.6, 57.4])**
- schema 有效率：195/200 (97.5%, CI [94.3, 98.9])
- 非法动作率（schema 合法但包络外）：2/200 (1.0%, CI [0.3, 3.6])
- 延迟 ms：p50=659 p95=735 max=2368

## 字段级准确率（有金标准条目）

| 字段 | 准确率 |
|---|---|
| mode | 199/200 (99.5%, CI [97.2, 99.9]) |
| formation | 71/200 (35.5%, CI [29.2, 42.3]) |
| ids | 191/200 (95.5%, CI [91.7, 97.6]) |
| tx | 197/200 (98.5%, CI [95.7, 99.5]) |
| ty | 197/200 (98.5%, CI [95.7, 99.5]) |
| tz | 105/200 (52.5%, CI [45.6, 59.3]) |

- 坐标 MAE-x: 0.377 m (bootstrap 95% CI [0.000, 0.980], n=199)
- 坐标 MAE-y: 0.176 m (bootstrap 95% CI [0.000, 0.528], n=199)
- 坐标 MAE-z: 4.286 m (bootstrap 95% CI [3.568, 5.050], n=199)

## 按类别

| category | n | 主指标 | schema | 非法 |
|---|---|---|---|---|
| ASSEMBLE | 40 | 34/40 (85.0%, CI [70.9, 92.9]) | 39/40 | 0 |
| HOLD | 40 | 40/40 (100.0%, CI [91.2, 100.0]) | 40/40 | 0 |
| OBSTACLE_AVOID | 40 | 17/40 (42.5%, CI [28.5, 57.8]) | 40/40 | 2 |
| RECON | 40 | 10/40 (25.0%, CI [14.2, 40.2]) | 40/40 | 0 |
| RECONFIGURE | 40 | 0/40 (0.0%, CI [0.0, 8.8]) | 36/40 | 0 |

## 失败样例（前 12 / 99）

- **P-003** [ASSEMBLE/ood] target-z: `All units, change formation.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 2, 3, 4], "target": [-30.0, 8.0, 5.0]}；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [1, 2, 3, 4], "target": [-30.0, 8.0, 15.0]}`
- **P-008** [OBSTACLE_AVOID/seen] target-z: `UAV 3 and 4, adjust formation.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [3, 4], "target": [20.0, 0.0, 15.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [3, 4], "target": [20.0, 0.0, 5.0]}`
- **P-009** [RECON/in-range-unseen] target-z: `All units, execute.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 2, 3, 4], "target": [142.0, 171.0, 15.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [142.0, 171.0, 5.0]}`
- **P-013** [ASSEMBLE/ood] target-z: `UAV 3, proceed.`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [3], "target": [25.0, 25.0, 5.0]}；输出 `{"mode": "single-agent", "formation": "free", "uav_ids": [3], "target": [25.0, 25.0, 25.0]}`
- **P-018** [RECON/seen] target-z: `Everyone, hold.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 2, 3, 4], "target": [200.0, 150.0, 15.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [200.0, 150.0, 5.0]}`
- **P-022** [RECONFIGURE/in] target-z: `Squad, take cover.`
  - 期望 {"mode": "swarm", "formation": "column", "uav_ids": [1, 2, 3, 4], "target": [15.0, 15.0, 8.0]}；输出 `{"mode": "swarm", "formation": "column", "uav_ids": [1, 2, 3, 4], "target": [15.0, 15.0, 15.0]}`
- **P-024** [RECONFIGURE/in] target-z: `All units, form up.`
  - 期望 {"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [15.0, 15.0, 8.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [15.0, 15.0, 15.0]}`
- **P-025** [OBSTACLE_AVOID/ood] target-z: `UAV 1 and 4, adjust formation.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 4], "target": [-10.0, 0.0, 15.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 4], "target": [-10.0, 0.0, 10.0]}`
- **P-026** [RECONFIGURE/in] target-z: `All units, evade.`
  - 期望 {"mode": "swarm", "formation": "wedge", "uav_ids": [1, 2, 3, 4], "target": [15.0, 15.0, 8.0]}；输出 `{"mode": "swarm", "formation": "wedge", "uav_ids": [1, 2, 3, 4], "target": [15.0, 15.0, 15.0]}`
- **P-027** [RECON/seen] target-z: `UAV 2 and 3, adjust formation.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [2, 3], "target": [168.0, 195.0, 15.0]}；输出 `{"mode": "swarm", "formation": "wedge", "uav_ids": [2, 3], "target": [168.0, 195.0, 5.0]}`
- **P-029** [OBSTACLE_AVOID/ood] target-x: `UAV 2, change position.`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [2], "target": [-60.0, 0.0, 15.0]}；输出 `{"mode": "single-agent", "formation": "free", "uav_ids": [2], "target": [-15.0, 0.0, 15.0]}`
- **P-030** [RECONFIGURE/in] target-z: `UAV 2, proceed.`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [2], "target": [15.0, 15.0, 8.0]}；输出 `{"mode": "single-agent", "formation": "free", "uav_ids": [2], "target": [15.0, 15.0, 15.0]}`

