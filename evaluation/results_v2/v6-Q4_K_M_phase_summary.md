# v6-Q4_K_M · phase 评测汇总（v2 六指标）

- 模型 `phi2-v6-q4_k_m.gguf` | n=200 | 2026-10-13 09:54:23 | 显存 3198MB | 耗时 121.2s

## 六指标总览

- 主指标（按 judge 类型）：**129/200 (64.5%, CI [57.7, 70.8])**
- schema 有效率：200/200 (100.0%, CI [98.1, 100.0])
- 非法动作率（schema 合法但包络外）：0/200 (0.0%, CI [0.0, 1.9])
- 延迟 ms：p50=536 p95=1557 max=1796

## 字段级准确率（有金标准条目）

| 字段 | 准确率 |
|---|---|
| mode | 150/200 (75.0%, CI [68.6, 80.5]) |
| formation | 38/200 (19.0%, CI [14.2, 25.0]) |
| ids | 112/200 (56.0%, CI [49.1, 62.7]) |
| tx | 195/200 (97.5%, CI [94.3, 98.9]) |
| ty | 200/200 (100.0%, CI [98.1, 100.0]) |
| tz | 134/200 (67.0%, CI [60.2, 73.1]) |

- 坐标 MAE-x: 0.860 m (bootstrap 95% CI [0.220, 1.750], n=200)
- 坐标 MAE-y: 0.000 m (bootstrap 95% CI [0.000, 0.000], n=200)
- 坐标 MAE-z: 2.400 m (bootstrap 95% CI [1.905, 2.935], n=200)

## 按类别

| category | n | 主指标 | schema | 非法 |
|---|---|---|---|---|
| ASSEMBLE | 40 | 20/40 (50.0%, CI [35.2, 64.8]) | 40/40 | 0 |
| HOLD | 40 | 40/40 (100.0%, CI [91.2, 100.0]) | 40/40 | 0 |
| OBSTACLE_AVOID | 40 | 34/40 (85.0%, CI [70.9, 92.9]) | 40/40 | 0 |
| RECON | 40 | 35/40 (87.5%, CI [73.9, 94.5]) | 40/40 | 0 |
| RECONFIGURE | 40 | 0/40 (0.0%, CI [0.0, 8.8]) | 40/40 | 0 |

## 失败样例（前 12 / 71）

- **P-001** [ASSEMBLE/in-range-unseen] target-z: `Everyone, scout ahead.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 2, 3, 4], "target": [0.0, -10.0, 5.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3], "target": [0.0, -10.0, 15.0]}`
- **P-010** [ASSEMBLE/ood] target-z: `UAV 2, proceed.`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [2], "target": [18.0, 0.0, 5.0]}；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [2], "target": [18.0, 0.0, 15.0]}`
- **P-013** [ASSEMBLE/ood] target-z: `UAV 3, proceed.`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [3], "target": [25.0, 25.0, 5.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [3], "target": [25.0, 25.0, 15.0]}`
- **P-018** [RECON/seen] target-z: `Everyone, hold.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 2, 3, 4], "target": [200.0, 150.0, 15.0]}；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [1, 2, 3], "target": [200.0, 150.0, 5.0]}`
- **P-020** [OBSTACLE_AVOID/seen] target-x: `UAV 3 and 4, adjust formation.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [3, 4], "target": [-15.0, 0.0, 15.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [3, 4], "target": [15.0, 0.0, 15.0]}`
- **P-021** [ASSEMBLE/in-range-unseen] target-z: `Squad, take cover.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 2, 3, 4], "target": [0.0, 3.0, 5.0]}；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [1, 2, 3], "target": [0.0, 3.0, 15.0]}`
- **P-022** [RECONFIGURE/in] target-z: `Squad, take cover.`
  - 期望 {"mode": "swarm", "formation": "column", "uav_ids": [1, 2, 3, 4], "target": [15.0, 15.0, 8.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3], "target": [15.0, 15.0, 15.0]}`
- **P-024** [RECONFIGURE/in] target-z: `All units, form up.`
  - 期望 {"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [15.0, 15.0, 8.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3], "target": [15.0, 15.0, 15.0]}`
- **P-025** [OBSTACLE_AVOID/ood] target-z: `UAV 1 and 4, adjust formation.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 4], "target": [-10.0, 0.0, 15.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 4], "target": [-10.0, 0.0, 10.0]}`
- **P-026** [RECONFIGURE/in] target-z: `All units, evade.`
  - 期望 {"mode": "swarm", "formation": "wedge", "uav_ids": [1, 2, 3, 4], "target": [15.0, 15.0, 8.0]}；输出 `{"mode": "swarm", "formation": "wedge", "uav_ids": [1, 2, 3], "target": [15.0, 15.0, 15.0]}`
- **P-030** [RECONFIGURE/in] target-z: `UAV 2, proceed.`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [2], "target": [15.0, 15.0, 8.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [2], "target": [15.0, 15.0, 5.0]}`
- **P-036** [RECONFIGURE/in] target-z: `UAV 3 and 4, tighten up.`
  - 期望 {"mode": "swarm", "formation": "column", "uav_ids": [3, 4], "target": [15.0, 15.0, 8.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [3, 4], "target": [15.0, 15.0, 5.0]}`

