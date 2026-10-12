# v5-FP16 · phase 评测汇总（v2 六指标）

- 模型 `phi2-fp16.gguf` | n=200 | 2026-10-12 21:14:48 | 显存 5901MB | 耗时 622.9s

## 六指标总览

- 主指标（按 judge 类型）：**106/200 (53.0%, CI [46.1, 59.8])**
- schema 有效率：194/200 (97.0%, CI [93.6, 98.6])
- 非法动作率（schema 合法但包络外）：2/200 (1.0%, CI [0.3, 3.6])
- 延迟 ms：p50=3306 p95=3803 max=4100

## 字段级准确率（有金标准条目）

| 字段 | 准确率 |
|---|---|
| mode | 200/200 (100.0%, CI [98.1, 100.0]) |
| formation | 73/200 (36.5%, CI [30.1, 43.4]) |
| ids | 186/200 (93.0%, CI [88.6, 95.8]) |
| tx | 197/200 (98.5%, CI [95.7, 99.5]) |
| ty | 193/200 (96.5%, CI [93.0, 98.3]) |
| tz | 111/200 (55.5%, CI [48.6, 62.2]) |

- 坐标 MAE-x: 0.152 m (bootstrap 95% CI [0.000, 0.455], n=198)
- 坐标 MAE-y: 0.682 m (bootstrap 95% CI [0.152, 1.288], n=198)
- 坐标 MAE-z: 3.758 m (bootstrap 95% CI [3.076, 4.505], n=198)

## 按类别

| category | n | 主指标 | schema | 非法 |
|---|---|---|---|---|
| ASSEMBLE | 40 | 28/40 (70.0%, CI [54.6, 81.9]) | 38/40 | 1 |
| HOLD | 40 | 40/40 (100.0%, CI [91.2, 100.0]) | 40/40 | 0 |
| OBSTACLE_AVOID | 40 | 20/40 (50.0%, CI [35.2, 64.8]) | 40/40 | 1 |
| RECON | 40 | 18/40 (45.0%, CI [30.7, 60.2]) | 40/40 | 0 |
| RECONFIGURE | 40 | 0/40 (0.0%, CI [0.0, 8.8]) | 36/40 | 0 |

## 失败样例（前 12 / 94）

- **P-003** [ASSEMBLE/ood] target-z: `All units, change formation.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 2, 3, 4], "target": [-30.0, 8.0, 5.0]}；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [1, 2, 3, 4], "target": [-30.0, 8.0, 15.0]}`
- **P-008** [OBSTACLE_AVOID/seen] target-z: `UAV 3 and 4, adjust formation.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [3, 4], "target": [20.0, 0.0, 15.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [3, 4], "target": [20.0, 0.0, 20.0]}`
- **P-009** [RECON/in-range-unseen] target-z: `All units, execute.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 2, 3, 4], "target": [142.0, 171.0, 15.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [142.0, 171.0, 5.0]}`
- **P-013** [ASSEMBLE/ood] target-z: `UAV 3, proceed.`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [3], "target": [25.0, 25.0, 5.0]}；输出 `{"mode": "single-agent", "formation": "free", "uav_ids": [3], "target": [25.0, 25.0, 25.0]}`
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
- **P-036** [RECONFIGURE/in] target-z: `UAV 3 and 4, tighten up.`
  - 期望 {"mode": "swarm", "formation": "column", "uav_ids": [3, 4], "target": [15.0, 15.0, 8.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [3, 4], "target": [15.0, 15.0, 15.0]}`

