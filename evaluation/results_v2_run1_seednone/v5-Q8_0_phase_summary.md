# v5-Q8_0 · phase 评测汇总（v2 六指标）

- 模型 `phi2-v5-q8_0.gguf` | n=200 | 2026-10-12 12:03:09 | 显存 3992MB | 耗时 109.3s

## 六指标总览

- 主指标（按 judge 类型）：**115/200 (57.5%, CI [50.6, 64.1])**
- schema 有效率：192/200 (96.0%, CI [92.3, 98.0])
- 非法动作率（schema 合法但包络外）：0/200 (0.0%, CI [0.0, 1.9])
- 延迟 ms：p50=538 p95=591 max=673

## 字段级准确率（有金标准条目）

| 字段 | 准确率 |
|---|---|
| mode | 200/200 (100.0%, CI [98.1, 100.0]) |
| formation | 74/200 (37.0%, CI [30.6, 43.9]) |
| ids | 172/200 (86.0%, CI [80.5, 90.1]) |
| tx | 195/200 (97.5%, CI [94.3, 98.9]) |
| ty | 194/200 (97.0%, CI [93.6, 98.6]) |
| tz | 120/200 (60.0%, CI [53.1, 66.5]) |

- 坐标 MAE-x: 0.153 m (bootstrap 95% CI [0.000, 0.459], n=196)
- 坐标 MAE-y: 0.230 m (bootstrap 95% CI [0.000, 0.612], n=196)
- 坐标 MAE-z: 3.189 m (bootstrap 95% CI [2.587, 3.811], n=196)

## 按类别

| category | n | 主指标 | schema | 非法 |
|---|---|---|---|---|
| ASSEMBLE | 40 | 23/40 (57.5%, CI [42.2, 71.5]) | 36/40 | 0 |
| HOLD | 40 | 40/40 (100.0%, CI [91.2, 100.0]) | 40/40 | 0 |
| OBSTACLE_AVOID | 40 | 21/40 (52.5%, CI [37.5, 67.1]) | 40/40 | 0 |
| RECON | 40 | 31/40 (77.5%, CI [62.5, 87.7]) | 40/40 | 0 |
| RECONFIGURE | 40 | 0/40 (0.0%, CI [0.0, 8.8]) | 36/40 | 0 |

## 失败样例（前 12 / 85）

- **P-003** [ASSEMBLE/ood] target-z: `All units, change formation.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 2, 3, 4], "target": [-30.0, 8.0, 5.0]}；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [1, 2, 3, 4], "target": [-30.0, 8.0, 15.0]}`
- **P-008** [OBSTACLE_AVOID/seen] target-z: `UAV 3 and 4, adjust formation.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [3, 4], "target": [20.0, 0.0, 15.0]}；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [3, 4], "target": [20.0, 0.0, 20.0]}`
- **P-009** [RECON/in-range-unseen] target-z: `All units, execute.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 2, 3, 4], "target": [142.0, 171.0, 15.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [142.0, 171.0, 5.0]}`
- **P-013** [ASSEMBLE/ood] target-z: `UAV 3, proceed.`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [3], "target": [25.0, 25.0, 5.0]}；输出 `{"mode": "single-agent", "formation": "free", "uav_ids": [3], "target": [25.0, 25.0, 25.0]}`
- **P-021** [ASSEMBLE/in-range-unseen] target-z: `Squad, take cover.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 2, 3, 4], "target": [0.0, 3.0, 5.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3], "target": [0.0, 3.0, 15.0]}`
- **P-022** [RECONFIGURE/in] target-z: `Squad, take cover.`
  - 期望 {"mode": "swarm", "formation": "column", "uav_ids": [1, 2, 3, 4], "target": [15.0, 15.0, 8.0]}；输出 `{"mode": "swarm", "formation": "column", "uav_ids": [1, 2, 3, 4], "target": [15.0, 15.0, 15.0]}`
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

