# v5-Q4_K_M · phase 评测汇总（v2 六指标）

- 模型 `phi2-v5-q4_k_m.gguf` | n=200 | 2026-10-12 12:20:12 | 显存 3538MB | 耗时 99.4s

## 六指标总览

- 主指标（按 judge 类型）：**86/200 (43.0%, CI [36.3, 49.9])**
- schema 有效率：195/200 (97.5%, CI [94.3, 98.9])
- 非法动作率（schema 合法但包络外）：0/200 (0.0%, CI [0.0, 1.9])
- 延迟 ms：p50=492 p95=540 max=610

## 字段级准确率（有金标准条目）

| 字段 | 准确率 |
|---|---|
| mode | 200/200 (100.0%, CI [98.1, 100.0]) |
| formation | 72/200 (36.0%, CI [29.7, 42.9]) |
| ids | 190/200 (95.0%, CI [91.0, 97.3]) |
| tx | 196/200 (98.0%, CI [95.0, 99.2]) |
| ty | 192/200 (96.0%, CI [92.3, 98.0]) |
| tz | 87/200 (43.5%, CI [36.8, 50.4]) |

- 坐标 MAE-x: 0.715 m (bootstrap 95% CI [0.120, 1.540], n=200)
- 坐标 MAE-y: 0.800 m (bootstrap 95% CI [0.300, 1.450], n=200)
- 坐标 MAE-z: 4.845 m (bootstrap 95% CI [4.200, 5.495], n=200)

## 按类别

| category | n | 主指标 | schema | 非法 |
|---|---|---|---|---|
| ASSEMBLE | 40 | 17/40 (42.5%, CI [28.5, 57.8]) | 40/40 | 0 |
| HOLD | 40 | 40/40 (100.0%, CI [91.2, 100.0]) | 40/40 | 0 |
| OBSTACLE_AVOID | 40 | 10/40 (25.0%, CI [14.2, 40.2]) | 40/40 | 0 |
| RECON | 40 | 19/40 (47.5%, CI [32.9, 62.5]) | 40/40 | 0 |
| RECONFIGURE | 40 | 0/40 (0.0%, CI [0.0, 8.8]) | 35/40 | 0 |

## 失败样例（前 12 / 114）

- **P-001** [ASSEMBLE/in-range-unseen] target-z: `Everyone, scout ahead.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 2, 3, 4], "target": [0.0, -10.0, 5.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [0.0, -10.0, 15.0]}`
- **P-003** [ASSEMBLE/ood] target-z: `All units, change formation.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 2, 3, 4], "target": [-30.0, 8.0, 5.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [-30.0, 8.0, 15.0]}`
- **P-008** [OBSTACLE_AVOID/seen] target-z: `UAV 3 and 4, adjust formation.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [3, 4], "target": [20.0, 0.0, 15.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [3, 4], "target": [20.0, 0.0, 20.0]}`
- **P-009** [RECON/in-range-unseen] target-z: `All units, execute.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 2, 3, 4], "target": [142.0, 171.0, 15.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [142.0, 171.0, 5.0]}`
- **P-010** [ASSEMBLE/ood] target-z: `UAV 2, proceed.`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [2], "target": [18.0, 0.0, 5.0]}；输出 `{"mode": "single-agent", "formation": "free", "uav_ids": [2], "target": [18.0, 0.0, 15.0]}`
- **P-013** [ASSEMBLE/ood] target-z: `UAV 3, proceed.`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [3], "target": [25.0, 25.0, 5.0]}；输出 `{"mode": "single-agent", "formation": "free", "uav_ids": [3], "target": [25.0, 25.0, 25.0]}`
- **P-021** [ASSEMBLE/in-range-unseen] target-z: `Squad, take cover.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 2, 3, 4], "target": [0.0, 3.0, 5.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3], "target": [0.0, 3.0, 15.0]}`
- **P-022** [RECONFIGURE/in] target-y: `Squad, take cover.`
  - 期望 {"mode": "swarm", "formation": "column", "uav_ids": [1, 2, 3, 4], "target": [15.0, 15.0, 8.0]}；输出 `{"mode": "swarm", "formation": "column", "uav_ids": [1, 2, 3, 4], "target": [15.0, -5.0, 15.0]}`
- **P-024** [RECONFIGURE/in] target-z: `All units, form up.`
  - 期望 {"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [15.0, 15.0, 8.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [15.0, 15.0, 15.0]}`
- **P-025** [OBSTACLE_AVOID/ood] target-z: `UAV 1 and 4, adjust formation.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 4], "target": [-10.0, 0.0, 15.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 4], "target": [-10.0, 0.0, 10.0]}`
- **P-026** [RECONFIGURE/in] target-y: `All units, evade.`
  - 期望 {"mode": "swarm", "formation": "wedge", "uav_ids": [1, 2, 3, 4], "target": [15.0, 15.0, 8.0]}；输出 `{"mode": "swarm", "formation": "wedge", "uav_ids": [1, 2, 3, 4], "target": [15.0, -5.0, 15.0]}`
- **P-027** [RECON/seen] target-z: `UAV 2 and 3, adjust formation.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [2, 3], "target": [168.0, 195.0, 15.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [2, 3], "target": [168.0, 195.0, 5.0]}`

