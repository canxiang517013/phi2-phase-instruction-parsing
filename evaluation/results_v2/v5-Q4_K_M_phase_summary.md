# v5-Q4_K_M · phase 评测汇总（v2 六指标）

- 模型 `phi2-v5-q4_k_m.gguf` | n=200 | 2026-10-12 21:54:48 | 显存 3528MB | 耗时 126.8s

## 六指标总览

- 主指标（按 judge 类型）：**83/200 (41.5%, CI [34.9, 48.4])**
- schema 有效率：194/200 (97.0%, CI [93.6, 98.6])
- 非法动作率（schema 合法但包络外）：0/200 (0.0%, CI [0.0, 1.9])
- 延迟 ms：p50=635 p95=697 max=886

## 字段级准确率（有金标准条目）

| 字段 | 准确率 |
|---|---|
| mode | 200/200 (100.0%, CI [98.1, 100.0]) |
| formation | 74/200 (37.0%, CI [30.6, 43.9]) |
| ids | 189/200 (94.5%, CI [90.4, 96.9]) |
| tx | 198/200 (99.0%, CI [96.4, 99.7]) |
| ty | 194/200 (97.0%, CI [93.6, 98.6]) |
| tz | 84/200 (42.0%, CI [35.4, 48.9]) |

- 坐标 MAE-x: 0.270 m (bootstrap 95% CI [0.000, 0.720], n=200)
- 坐标 MAE-y: 0.525 m (bootstrap 95% CI [0.125, 1.025], n=200)
- 坐标 MAE-z: 4.975 m (bootstrap 95% CI [4.320, 5.645], n=200)

## 按类别

| category | n | 主指标 | schema | 非法 |
|---|---|---|---|---|
| ASSEMBLE | 40 | 16/40 (40.0%, CI [26.3, 55.4]) | 40/40 | 0 |
| HOLD | 40 | 40/40 (100.0%, CI [91.2, 100.0]) | 40/40 | 0 |
| OBSTACLE_AVOID | 40 | 10/40 (25.0%, CI [14.2, 40.2]) | 40/40 | 0 |
| RECON | 40 | 17/40 (42.5%, CI [28.5, 57.8]) | 40/40 | 0 |
| RECONFIGURE | 40 | 0/40 (0.0%, CI [0.0, 8.8]) | 34/40 | 0 |

## 失败样例（前 12 / 117）

- **P-001** [ASSEMBLE/in-range-unseen] target-z: `Everyone, scout ahead.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 2, 3, 4], "target": [0.0, -10.0, 5.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [0.0, -10.0, 15.0]}`
- **P-003** [ASSEMBLE/ood] target-z: `All units, change formation.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 2, 3, 4], "target": [-30.0, 8.0, 5.0]}；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [1, 2, 3, 4], "target": [-30.0, 8.0, 15.0]}`
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

