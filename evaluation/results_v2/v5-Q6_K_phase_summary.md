# v5-Q6_K · phase 评测汇总（v2 六指标）

- 模型 `phi2-v5-q6_k.gguf` | n=200 | 2026-10-12 21:40:11 | 显存 4176MB | 耗时 176.7s

## 六指标总览

- 主指标（按 judge 类型）：**105/200 (52.5%, CI [45.6, 59.3])**
- schema 有效率：191/200 (95.5%, CI [91.7, 97.6])
- 非法动作率（schema 合法但包络外）：2/200 (1.0%, CI [0.3, 3.6])
- 延迟 ms：p50=759 p95=2498 max=2826

## 字段级准确率（有金标准条目）

| 字段 | 准确率 |
|---|---|
| mode | 200/200 (100.0%, CI [98.1, 100.0]) |
| formation | 75/200 (37.5%, CI [31.1, 44.4]) |
| ids | 183/200 (91.5%, CI [86.8, 94.6]) |
| tx | 192/200 (96.0%, CI [92.3, 98.0]) |
| ty | 193/200 (96.5%, CI [93.0, 98.3]) |
| tz | 111/200 (55.5%, CI [48.6, 62.2]) |

- 坐标 MAE-x: 0.610 m (bootstrap 95% CI [0.000, 1.446], n=195)
- 坐标 MAE-y: 0.154 m (bootstrap 95% CI [0.000, 0.385], n=195)
- 坐标 MAE-z: 3.728 m (bootstrap 95% CI [3.000, 4.492], n=195)

## 按类别

| category | n | 主指标 | schema | 非法 |
|---|---|---|---|---|
| ASSEMBLE | 40 | 25/40 (62.5%, CI [47.0, 75.8]) | 35/40 | 0 |
| HOLD | 40 | 40/40 (100.0%, CI [91.2, 100.0]) | 40/40 | 0 |
| OBSTACLE_AVOID | 40 | 19/40 (47.5%, CI [32.9, 62.5]) | 40/40 | 2 |
| RECON | 40 | 21/40 (52.5%, CI [37.5, 67.1]) | 40/40 | 0 |
| RECONFIGURE | 40 | 0/40 (0.0%, CI [0.0, 8.8]) | 36/40 | 0 |

## 失败样例（前 12 / 95）

- **P-003** [ASSEMBLE/ood] target-z: `All units, change formation.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 2, 3, 4], "target": [-30.0, 8.0, 5.0]}；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [1, 2, 3, 4], "target": [-30.0, 8.0, 15.0]}`
- **P-008** [OBSTACLE_AVOID/seen] target-z: `UAV 3 and 4, adjust formation.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [3, 4], "target": [20.0, 0.0, 15.0]}；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [3, 4], "target": [20.0, 0.0, 20.0]}`
- **P-009** [RECON/in-range-unseen] target-z: `All units, execute.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 2, 3, 4], "target": [142.0, 171.0, 15.0]}；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [1, 2, 3, 4], "target": [142.0, 171.0, 5.0]}`
- **P-013** [ASSEMBLE/ood] target-z: `UAV 3, proceed.`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [3], "target": [25.0, 25.0, 5.0]}；输出 `{"mode": "single-agent", "formation": "free", "uav_ids": [3], "target": [25.0, 25.0, 25.0]}`
- **P-018** [RECON/seen] target-z: `Everyone, hold.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 2, 3, 4], "target": [200.0, 150.0, 15.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [200.0, 150.0, 5.0]}`
- **P-022** [RECONFIGURE/in] target-z: `Squad, take cover.`
  - 期望 {"mode": "swarm", "formation": "column", "uav_ids": [1, 2, 3, 4], "target": [15.0, 15.0, 8.0]}；输出 `{"mode": "swarm", "formation": "column", "uav_ids": [1, 2, 3], "target": [15.0, 15.0, 15.0]}`
- **P-024** [RECONFIGURE/in] target-z: `All units, form up.`
  - 期望 {"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [15.0, 15.0, 8.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [15.0, 15.0, 15.0]}`
- **P-025** [OBSTACLE_AVOID/ood] target-z: `UAV 1 and 4, adjust formation.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 4], "target": [-10.0, 0.0, 15.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 4], "target": [-10.0, 0.0, 10.0]}`
- **P-026** [RECONFIGURE/in] target-z: `All units, evade.`
  - 期望 {"mode": "swarm", "formation": "wedge", "uav_ids": [1, 2, 3, 4], "target": [15.0, 15.0, 8.0]}；输出 `{"mode": "swarm", "formation": "wedge", "uav_ids": [1, 2, 3, 4], "target": [15.0, 15.0, 15.0]}`
- **P-030** [RECONFIGURE/in] target-z: `UAV 2, proceed.`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [2], "target": [15.0, 15.0, 8.0]}；输出 `{"mode": "single-agent", "formation": "free", "uav_ids": [2], "target": [15.0, 15.0, 15.0]}`
- **P-032** [OBSTACLE_AVOID/in-range-unseen] target-z: `UAV 2, continue.`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [2], "target": [17.0, 0.0, 15.0]}；输出 `{"mode": "single-agent", "formation": "free", "uav_ids": [2], "target": [17.0, 0.0, 17.0]}`
- **P-034** [ASSEMBLE/in-range-unseen] target-z: `UAV 1, continue.`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [1], "target": [8.0, -2.0, 5.0]}；输出 `{"mode": "single-agent", "formation": "free", "uav_ids": [1], "target": [8.0, -2.0, 8.0]}`

