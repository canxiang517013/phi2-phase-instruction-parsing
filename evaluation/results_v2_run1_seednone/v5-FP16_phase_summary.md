# v5-FP16 · phase 评测汇总（v2 六指标）

- 模型 `phi2-fp16.gguf` | n=200 | 2026-10-12 11:52:39 | 显存 6011MB | 耗时 432.2s

## 六指标总览

- 主指标（按 judge 类型）：**105/200 (52.5%, CI [45.6, 59.3])**
- schema 有效率：193/200 (96.5%, CI [93.0, 98.3])
- 非法动作率（schema 合法但包络外）：1/200 (0.5%, CI [0.1, 2.8])
- 延迟 ms：p50=2155 p95=2334 max=2588

## 字段级准确率（有金标准条目）

| 字段 | 准确率 |
|---|---|
| mode | 200/200 (100.0%, CI [98.1, 100.0]) |
| formation | 74/200 (37.0%, CI [30.6, 43.9]) |
| ids | 186/200 (93.0%, CI [88.6, 95.8]) |
| tx | 197/200 (98.5%, CI [95.7, 99.5]) |
| ty | 193/200 (96.5%, CI [93.0, 98.3]) |
| tz | 110/200 (55.0%, CI [48.1, 61.7]) |

- 坐标 MAE-x: 0.152 m (bootstrap 95% CI [0.000, 0.455], n=198)
- 坐标 MAE-y: 0.682 m (bootstrap 95% CI [0.152, 1.288], n=198)
- 坐标 MAE-z: 3.641 m (bootstrap 95% CI [3.015, 4.298], n=198)

## 按类别

| category | n | 主指标 | schema | 非法 |
|---|---|---|---|---|
| ASSEMBLE | 40 | 29/40 (72.5%, CI [57.2, 83.9]) | 38/40 | 1 |
| HOLD | 40 | 40/40 (100.0%, CI [91.2, 100.0]) | 40/40 | 0 |
| OBSTACLE_AVOID | 40 | 20/40 (50.0%, CI [35.2, 64.8]) | 40/40 | 0 |
| RECON | 40 | 16/40 (40.0%, CI [26.3, 55.4]) | 40/40 | 0 |
| RECONFIGURE | 40 | 0/40 (0.0%, CI [0.0, 8.8]) | 35/40 | 0 |

## 失败样例（前 12 / 95）

- **P-003** [ASSEMBLE/ood] target-z: `All units, change formation.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 2, 3, 4], "target": [-30.0, 8.0, 5.0]}；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [1, 2, 3, 4], "target": [-30.0, 8.0, 15.0]}`
- **P-008** [OBSTACLE_AVOID/seen] target-z: `UAV 3 and 4, adjust formation.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [3, 4], "target": [20.0, 0.0, 15.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [3, 4], "target": [20.0, 0.0, 20.0]}`
- **P-009** [RECON/in-range-unseen] target-z: `All units, execute.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 2, 3, 4], "target": [142.0, 171.0, 15.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [142.0, 171.0, 5.0]}`
- **P-013** [ASSEMBLE/ood] target-z: `UAV 3, proceed.`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [3], "target": [25.0, 25.0, 5.0]}；输出 `{"mode": "single-agent", "formation": "free", "uav_ids": [3], "target": [25.0, 25.0, 25.0]}`
- **P-018** [RECON/seen] target-z: `Everyone, hold.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 2, 3, 4], "target": [200.0, 150.0, 15.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [200.0, 150.0, 5.0]}`
- **P-022** [RECONFIGURE/in] target-y: `Squad, take cover.`
  - 期望 {"mode": "swarm", "formation": "column", "uav_ids": [1, 2, 3, 4], "target": [15.0, 15.0, 8.0]}；输出 `{"mode": "swarm", "formation": "column", "uav_ids": [1, 2, 3, 4], "target": [15.0, -15.0, 5.0]}`
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

