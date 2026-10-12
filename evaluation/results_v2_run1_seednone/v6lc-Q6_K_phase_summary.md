# v6lc-Q6_K · phase 评测汇总（v2 六指标）

- 模型 `phi2-v6lc-q6_k.gguf` | n=200 | 2026-10-12 13:27:11 | 显存 4832MB | 耗时 131.2s

## 六指标总览

- 主指标（按 judge 类型）：**99/200 (49.5%, CI [42.6, 56.4])**
- schema 有效率：186/200 (93.0%, CI [88.6, 95.8])
- 非法动作率（schema 合法但包络外）：0/200 (0.0%, CI [0.0, 1.9])
- 延迟 ms：p50=641 p95=705 max=1054

## 字段级准确率（有金标准条目）

| 字段 | 准确率 |
|---|---|
| mode | 146/192 (76.0%, CI [69.5, 81.5]) |
| formation | 46/192 (24.0%, CI [18.5, 30.5]) |
| ids | 190/192 (99.0%, CI [96.3, 99.7]) |
| tx | 170/192 (88.5%, CI [83.3, 92.3]) |
| ty | 184/192 (95.8%, CI [92.0, 97.9]) |
| tz | 105/192 (54.7%, CI [47.6, 61.6]) |

- 坐标 MAE-x: 5.505 m (bootstrap 95% CI [3.042, 8.453], n=192)
- 坐标 MAE-y: 0.651 m (bootstrap 95% CI [0.234, 1.120], n=192)
- 坐标 MAE-z: 3.776 m (bootstrap 95% CI [3.068, 4.516], n=192)

## 按类别

| category | n | 主指标 | schema | 非法 |
|---|---|---|---|---|
| ASSEMBLE | 40 | 28/40 (70.0%, CI [54.6, 81.9]) | 38/40 | 0 |
| HOLD | 40 | 40/40 (100.0%, CI [91.2, 100.0]) | 40/40 | 0 |
| OBSTACLE_AVOID | 40 | 5/40 (12.5%, CI [5.5, 26.1]) | 39/40 | 0 |
| RECON | 40 | 26/40 (65.0%, CI [49.5, 77.9]) | 40/40 | 0 |
| RECONFIGURE | 40 | 0/40 (0.0%, CI [0.0, 8.8]) | 29/40 | 0 |

## 失败样例（前 12 / 101）

- **P-006** [ASSEMBLE/ood] target-z: `UAV 1, continue.`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [1], "target": [12.0, -9.0, 5.0]}；输出 `{"mode": "single-agent", "formation": "free", "uav_ids": [1], "target": [12.0, -9.0, 1.0]}`
- **P-008** [OBSTACLE_AVOID/seen] target-z: `UAV 3 and 4, adjust formation.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [3, 4], "target": [20.0, 0.0, 15.0]}；输出 `{"mode": "single-agent", "formation": "free", "uav_ids": [3, 4], "target": [20.0, 0.0, 0.0]}`
- **P-009** [RECON/in-range-unseen] target-z: `All units, execute.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 2, 3, 4], "target": [142.0, 171.0, 15.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [142.0, 171.0, 5.0]}`
- **P-010** [ASSEMBLE/ood] target-z: `UAV 2, proceed.`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [2], "target": [18.0, 0.0, 5.0]}；输出 `{"mode": "single-agent", "formation": "free", "uav_ids": [2], "target": [18.0, 0.0, 0.0]}`
- **P-011** [RECON/seen] target-z: `Squad, respond to the situation.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 2, 3, 4], "target": [225.0, 110.0, 15.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [225.0, 110.0, 5.0]}`
- **P-013** [ASSEMBLE/ood] target-z: `UAV 3, proceed.`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [3], "target": [25.0, 25.0, 5.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [3], "target": [25.0, 25.0, 15.0]}`
- **P-017** [ASSEMBLE/ood] target-z: `UAV 1, change position.`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [1], "target": [12.0, -9.0, 5.0]}；输出 `{"mode": "single-agent", "formation": "free", "uav_ids": [1], "target": [12.0, -9.0, 1.0]}`
- **P-019** [ASSEMBLE/ood] target-z: `UAV 1, continue.`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [1], "target": [-12.0, 15.0, 5.0]}；输出 `{"mode": "single-agent", "formation": "free", "uav_ids": [1], "target": [-12.0, 15.0, 1.0]}`
- **P-020** [OBSTACLE_AVOID/seen] target-x: `UAV 3 and 4, adjust formation.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [3, 4], "target": [-15.0, 0.0, 15.0]}；输出 `{"mode": "single-agent", "formation": "free", "uav_ids": [3, 4], "target": [15.0, 0.0, 15.0]}`
- **P-022** [RECONFIGURE/in] target-z: `Squad, take cover.`
  - 期望 {"mode": "swarm", "formation": "column", "uav_ids": [1, 2, 3, 4], "target": [15.0, 15.0, 8.0]}；输出 `{"mode": "swarm", "formation": "column", "uav_ids": [1, 2, 3, 4], "target": [15.0, 15.0, 5.0]}`
- **P-024** [RECONFIGURE/in] target-z: `All units, form up.`
  - 期望 {"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [15.0, 15.0, 8.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [15.0, 15.0, 5.0]}`
- **P-025** [OBSTACLE_AVOID/ood] target-x: `UAV 1 and 4, adjust formation.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 4], "target": [-10.0, 0.0, 15.0]}；输出 `{"mode": "single-agent", "formation": "free", "uav_ids": [1, 4], "target": [10.0, 0.0, 0.0]}`

