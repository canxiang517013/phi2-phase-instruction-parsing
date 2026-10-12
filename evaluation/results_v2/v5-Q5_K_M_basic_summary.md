# v5-Q5_K_M · basic 评测汇总（v2 六指标）

- 模型 `phi2-phased-v5-q5_k_m.gguf` | n=240 | 2026-10-12 21:45:34 | 显存 3764MB | 耗时 166.9s

## 六指标总览

- 主指标（按 judge 类型）：**238/240 (99.2%, CI [97.0, 99.8])**
- schema 有效率：239/240 (99.6%, CI [97.7, 99.9])
- 非法动作率（schema 合法但包络外）：0/240 (0.0%, CI [0.0, 1.6])
- 延迟 ms：p50=643 p95=708 max=2314

## 字段级准确率（有金标准条目）

| 字段 | 准确率 |
|---|---|
| mode | 239/240 (99.6%, CI [97.7, 99.9]) |
| formation | 240/240 (100.0%, CI [98.4, 100.0]) |
| ids | 240/240 (100.0%, CI [98.4, 100.0]) |
| tx | 240/240 (100.0%, CI [98.4, 100.0]) |
| ty | 239/240 (99.6%, CI [97.7, 99.9]) |
| tz | 240/240 (100.0%, CI [98.4, 100.0]) |

- 坐标 MAE-x: 0.000 m (bootstrap 95% CI [0.000, 0.000], n=240)
- 坐标 MAE-y: 0.222 m (bootstrap 95% CI [0.000, 0.666], n=240)
- 坐标 MAE-z: 0.000 m (bootstrap 95% CI [0.000, 0.000], n=240)

## 按类别

| category | n | 主指标 | schema | 非法 |
|---|---|---|---|---|
| single-agent | 90 | 90/90 (100.0%, CI [95.9, 100.0]) | 90/90 | 0 |
| swarm-circle | 30 | 29/30 (96.7%, CI [83.3, 99.4]) | 30/30 | 0 |
| swarm-grid | 30 | 30/30 (100.0%, CI [88.6, 100.0]) | 30/30 | 0 |
| swarm-line | 30 | 29/30 (96.7%, CI [83.3, 99.4]) | 29/30 | 0 |
| swarm-triangle | 30 | 30/30 (100.0%, CI [88.6, 100.0]) | 30/30 | 0 |
| swarm-wedge | 30 | 30/30 (100.0%, CI [88.6, 100.0]) | 30/30 | 0 |

## 失败样例（前 12 / 2）

- **B-100** [swarm-line/in] mode: `UAV 1, 2 and 3, line formation, target (6.3, -2.5, 2.1).`
  - 期望 {"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3], "target": [6.3, -2.5, 2.1]}；输出 `{"mode": "line", "formation": "line", "uav_ids": [1, 2, 3], "target": [6.3, -2.5, 2.1]}`
- **B-239** [swarm-circle/out] target: `Have UAV 2, 4 and 5 form up in a circle and proceed to (-9, -59.2, 10).`
  - 期望 {"mode": "swarm", "formation": "circle", "uav_ids": [2, 4, 5], "target": [-9.0, -59.2, 10.0]}；输出 `{"mode": "swarm", "formation": "circle", "uav_ids": [2, 4, 5], "target": [-9.0, -5.9, 10.0]}`

