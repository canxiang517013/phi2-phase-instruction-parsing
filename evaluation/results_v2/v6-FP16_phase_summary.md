# v6-FP16 · phase 评测汇总（v2 六指标）

- 模型 `phi2-v6-fp16.gguf` | n=200 | 2026-10-13 09:29:32 | 显存 6025MB | 耗时 615.1s

## 六指标总览

- 主指标（按 judge 类型）：**110/200 (55.0%, CI [48.1, 61.7])**
- schema 有效率：199/200 (99.5%, CI [97.2, 99.9])
- 非法动作率（schema 合法但包络外）：0/200 (0.0%, CI [0.0, 1.9])
- 延迟 ms：p50=3032 p95=3630 max=3908

## 字段级准确率（有金标准条目）

| 字段 | 准确率 |
|---|---|
| mode | 144/200 (72.0%, CI [65.4, 77.8]) |
| formation | 39/200 (19.5%, CI [14.6, 25.5]) |
| ids | 152/200 (76.0%, CI [69.6, 81.4]) |
| tx | 186/200 (93.0%, CI [88.6, 95.8]) |
| ty | 199/200 (99.5%, CI [97.2, 99.9]) |
| tz | 122/200 (61.0%, CI [54.1, 67.5]) |

- 坐标 MAE-x: 3.729 m (bootstrap 95% CI [1.819, 6.121], n=199)
- 坐标 MAE-y: 0.000 m (bootstrap 95% CI [0.000, 0.000], n=199)
- 坐标 MAE-z: 2.608 m (bootstrap 95% CI [2.075, 3.166], n=199)

## 按类别

| category | n | 主指标 | schema | 非法 |
|---|---|---|---|---|
| ASSEMBLE | 40 | 32/40 (80.0%, CI [65.2, 89.5]) | 39/40 | 0 |
| HOLD | 40 | 40/40 (100.0%, CI [91.2, 100.0]) | 40/40 | 0 |
| OBSTACLE_AVOID | 40 | 20/40 (50.0%, CI [35.2, 64.8]) | 40/40 | 0 |
| RECON | 40 | 18/40 (45.0%, CI [30.7, 60.2]) | 40/40 | 0 |
| RECONFIGURE | 40 | 0/40 (0.0%, CI [0.0, 8.8]) | 40/40 | 0 |

## 失败样例（前 12 / 90）

- **P-001** [ASSEMBLE/in-range-unseen] target-z: `Everyone, scout ahead.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 2, 3, 4], "target": [0.0, -10.0, 5.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [0.0, -10.0, 15.0]}`
- **P-008** [OBSTACLE_AVOID/seen] target-z: `UAV 3 and 4, adjust formation.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [3, 4], "target": [20.0, 0.0, 15.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [3, 4], "target": [20.0, 0.0, 5.0]}`
- **P-009** [RECON/in-range-unseen] target-z: `All units, execute.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 2, 3, 4], "target": [142.0, 171.0, 15.0]}；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [1, 2, 3, 4], "target": [142.0, 171.0, 5.0]}`
- **P-018** [RECON/seen] target-z: `Everyone, hold.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 2, 3, 4], "target": [200.0, 150.0, 15.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [200.0, 150.0, 5.0]}`
- **P-020** [OBSTACLE_AVOID/seen] target-x: `UAV 3 and 4, adjust formation.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [3, 4], "target": [-15.0, 0.0, 15.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [3, 4], "target": [15.0, 0.0, 15.0]}`
- **P-022** [RECONFIGURE/in] target-z: `Squad, take cover.`
  - 期望 {"mode": "swarm", "formation": "column", "uav_ids": [1, 2, 3, 4], "target": [15.0, 15.0, 8.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3], "target": [15.0, 15.0, 5.0]}`
- **P-024** [RECONFIGURE/in] target-z: `All units, form up.`
  - 期望 {"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [15.0, 15.0, 8.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [15.0, 15.0, 5.0]}`
- **P-025** [OBSTACLE_AVOID/ood] target-x: `UAV 1 and 4, adjust formation.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 4], "target": [-10.0, 0.0, 15.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 4], "target": [10.0, 0.0, 5.0]}`
- **P-026** [RECONFIGURE/in] target-z: `All units, evade.`
  - 期望 {"mode": "swarm", "formation": "wedge", "uav_ids": [1, 2, 3, 4], "target": [15.0, 15.0, 8.0]}；输出 `{"mode": "swarm", "formation": "wedge", "uav_ids": [1, 2, 3], "target": [15.0, 15.0, 15.0]}`
- **P-027** [RECON/seen] target-z: `UAV 2 and 3, adjust formation.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [2, 3], "target": [168.0, 195.0, 15.0]}；输出 `{"mode": "swarm", "formation": "wedge", "uav_ids": [2, 3], "target": [168.0, 195.0, 5.0]}`
- **P-030** [RECONFIGURE/in] target-z: `UAV 2, proceed.`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [2], "target": [15.0, 15.0, 8.0]}；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [2], "target": [15.0, 15.0, 5.0]}`
- **P-032** [OBSTACLE_AVOID/in-range-unseen] target-z: `UAV 2, continue.`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [2], "target": [17.0, 0.0, 15.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [2], "target": [17.0, 0.0, 5.0]}`

