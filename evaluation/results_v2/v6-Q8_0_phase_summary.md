# v6-Q8_0 · phase 评测汇总（v2 六指标）

- 模型 `phi2-v6-q8_0.gguf` | n=200 | 2026-10-13 09:47:16 | 显存 3863MB | 耗时 178.4s

## 六指标总览

- 主指标（按 judge 类型）：**100/200 (50.0%, CI [43.1, 56.9])**
- schema 有效率：199/200 (99.5%, CI [97.2, 99.9])
- 非法动作率（schema 合法但包络外）：0/200 (0.0%, CI [0.0, 1.9])
- 延迟 ms：p50=599 p95=1413 max=1493

## 字段级准确率（有金标准条目）

| 字段 | 准确率 |
|---|---|
| mode | 144/200 (72.0%, CI [65.4, 77.8]) |
| formation | 32/200 (16.0%, CI [11.6, 21.7]) |
| ids | 151/200 (75.5%, CI [69.1, 80.9]) |
| tx | 185/200 (92.5%, CI [88.0, 95.4]) |
| ty | 199/200 (99.5%, CI [97.2, 99.9]) |
| tz | 113/200 (56.5%, CI [49.6, 63.2]) |

- 坐标 MAE-x: 4.332 m (bootstrap 95% CI [2.161, 7.095], n=199)
- 坐标 MAE-y: 0.005 m (bootstrap 95% CI [0.000, 0.015], n=199)
- 坐标 MAE-z: 3.060 m (bootstrap 95% CI [2.467, 3.643], n=199)

## 按类别

| category | n | 主指标 | schema | 非法 |
|---|---|---|---|---|
| ASSEMBLE | 40 | 27/40 (67.5%, CI [52.0, 79.9]) | 39/40 | 0 |
| HOLD | 40 | 40/40 (100.0%, CI [91.2, 100.0]) | 40/40 | 0 |
| OBSTACLE_AVOID | 40 | 19/40 (47.5%, CI [32.9, 62.5]) | 40/40 | 0 |
| RECON | 40 | 14/40 (35.0%, CI [22.1, 50.5]) | 40/40 | 0 |
| RECONFIGURE | 40 | 0/40 (0.0%, CI [0.0, 8.8]) | 40/40 | 0 |

## 失败样例（前 12 / 100）

- **P-008** [OBSTACLE_AVOID/seen] target-z: `UAV 3 and 4, adjust formation.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [3, 4], "target": [20.0, 0.0, 15.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [3, 4], "target": [20.0, 0.0, 5.0]}`
- **P-009** [RECON/in-range-unseen] target-z: `All units, execute.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 2, 3, 4], "target": [142.0, 171.0, 15.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [142.0, 171.0, 5.0]}`
- **P-013** [ASSEMBLE/ood] target-z: `UAV 3, proceed.`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [3], "target": [25.0, 25.0, 5.0]}；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [3], "target": [25.0, 25.0, 15.0]}`
- **P-018** [RECON/seen] target-z: `Everyone, hold.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 2, 3, 4], "target": [200.0, 150.0, 15.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [200.0, 150.0, 5.0]}`
- **P-020** [OBSTACLE_AVOID/seen] target-x: `UAV 3 and 4, adjust formation.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [3, 4], "target": [-15.0, 0.0, 15.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [3, 4], "target": [15.0, 0.0, 15.0]}`
- **P-022** [RECONFIGURE/in] target-z: `Squad, take cover.`
  - 期望 {"mode": "swarm", "formation": "column", "uav_ids": [1, 2, 3, 4], "target": [15.0, 15.0, 8.0]}；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [1, 2, 3, 4], "target": [15.0, 15.0, 5.0]}`
- **P-024** [RECONFIGURE/in] target-z: `All units, form up.`
  - 期望 {"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [15.0, 15.0, 8.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [15.0, 15.0, 5.0]}`
- **P-025** [OBSTACLE_AVOID/ood] target-x: `UAV 1 and 4, adjust formation.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 4], "target": [-10.0, 0.0, 15.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 4], "target": [10.0, 0.0, 5.0]}`
- **P-026** [RECONFIGURE/in] target-z: `All units, evade.`
  - 期望 {"mode": "swarm", "formation": "wedge", "uav_ids": [1, 2, 3, 4], "target": [15.0, 15.0, 8.0]}；输出 `{"mode": "swarm", "formation": "wedge", "uav_ids": [1, 2, 3], "target": [15.0, 15.0, 15.0]}`
- **P-027** [RECON/seen] target-z: `UAV 2 and 3, adjust formation.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [2, 3], "target": [168.0, 195.0, 15.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [2, 3], "target": [168.0, 195.0, 5.0]}`
- **P-029** [OBSTACLE_AVOID/ood] target-x: `UAV 2, change position.`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [2], "target": [-60.0, 0.0, 15.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [2], "target": [60.0, 0.0, 15.0]}`
- **P-030** [RECONFIGURE/in] target-z: `UAV 2, proceed.`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [2], "target": [15.0, 15.0, 8.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [2], "target": [15.0, 15.0, 5.0]}`

