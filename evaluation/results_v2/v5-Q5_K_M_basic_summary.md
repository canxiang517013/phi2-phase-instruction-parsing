# v5-Q5_K_M · basic 评测汇总（v2 六指标）

- 模型 `phi2-phased-v5-q5_k_m.gguf` | n=240 | 2026-10-12 12:13:12 | 显存 3695MB | 耗时 124.7s

## 六指标总览

- 主指标（按 judge 类型）：**234/240 (97.5%, CI [94.7, 98.8])**
- schema 有效率：236/240 (98.3%, CI [95.8, 99.4])
- 非法动作率（schema 合法但包络外）：0/240 (0.0%, CI [0.0, 1.6])
- 延迟 ms：p50=519 p95=549 max=576

## 字段级准确率（有金标准条目）

| 字段 | 准确率 |
|---|---|
| mode | 236/240 (98.3%, CI [95.8, 99.4]) |
| formation | 237/240 (98.8%, CI [96.4, 99.6]) |
| ids | 240/240 (100.0%, CI [98.4, 100.0]) |
| tx | 240/240 (100.0%, CI [98.4, 100.0]) |
| ty | 238/240 (99.2%, CI [97.0, 99.8]) |
| tz | 240/240 (100.0%, CI [98.4, 100.0]) |

- 坐标 MAE-x: 0.000 m (bootstrap 95% CI [0.000, 0.000], n=240)
- 坐标 MAE-y: 0.449 m (bootstrap 95% CI [0.000, 1.129], n=240)
- 坐标 MAE-z: 0.000 m (bootstrap 95% CI [0.000, 0.000], n=240)

## 按类别

| category | n | 主指标 | schema | 非法 |
|---|---|---|---|---|
| single-agent | 90 | 90/90 (100.0%, CI [95.9, 100.0]) | 90/90 | 0 |
| swarm-circle | 30 | 28/30 (93.3%, CI [78.7, 98.2]) | 30/30 | 0 |
| swarm-grid | 30 | 28/30 (93.3%, CI [78.7, 98.2]) | 28/30 | 0 |
| swarm-line | 30 | 28/30 (93.3%, CI [78.7, 98.2]) | 28/30 | 0 |
| swarm-triangle | 30 | 30/30 (100.0%, CI [88.6, 100.0]) | 30/30 | 0 |
| swarm-wedge | 30 | 30/30 (100.0%, CI [88.6, 100.0]) | 30/30 | 0 |

## 失败样例（前 12 / 6）

- **B-100** [swarm-line/in] mode: `UAV 1, 2 and 3, line formation, target (6.3, -2.5, 2.1).`
  - 期望 {"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3], "target": [6.3, -2.5, 2.1]}；输出 `{"mode": "line", "formation": "line", "uav_ids": [1, 2, 3], "target": [6.3, -2.5, 2.1]}`
- **B-109** [swarm-line/in] mode: `UAV 1, 3 and 5, line formation, target (-11.6, -15.1, 4.5).`
  - 期望 {"mode": "swarm", "formation": "line", "uav_ids": [1, 3, 5], "target": [-11.6, -15.1, 4.5]}；输出 `{"mode": "line", "formation": "free", "uav_ids": [1, 3, 5], "target": [-11.6, -15.1, 4.5]}`
- **B-157** [swarm-grid/in] mode: `UAV 2, 3 and 5, grid formation, target (-17.3, 2.4, 11.1).`
  - 期望 {"mode": "swarm", "formation": "grid", "uav_ids": [2, 3, 5], "target": [-17.3, 2.4, 11.1]}；输出 `{"mode": "grid", "formation": "free", "uav_ids": [2, 3, 5], "target": [-17.3, 2.4, 11.1]}`
- **B-179** [swarm-grid/out] mode: `UAV 2 and 3, grid formation, target (-45.9, 4.1, 4.4).`
  - 期望 {"mode": "swarm", "formation": "grid", "uav_ids": [2, 3], "target": [-45.9, 4.1, 4.4]}；输出 `{"mode": "grid", "formation": "free", "uav_ids": [2, 3], "target": [-45.9, 4.1, 4.4]}`
- **B-235** [swarm-circle/out] target: `Have UAV 3 and 4 form up in a circle and proceed to (-13, -59.4, 18).`
  - 期望 {"mode": "swarm", "formation": "circle", "uav_ids": [3, 4], "target": [-13.0, -59.4, 18.0]}；输出 `{"mode": "swarm", "formation": "circle", "uav_ids": [3, 4], "target": [-13.0, -5.0, 18.0]}`
- **B-239** [swarm-circle/out] target: `Have UAV 2, 4 and 5 form up in a circle and proceed to (-9, -59.2, 10).`
  - 期望 {"mode": "swarm", "formation": "circle", "uav_ids": [2, 4, 5], "target": [-9.0, -59.2, 10.0]}；输出 `{"mode": "swarm", "formation": "circle", "uav_ids": [2, 4, 5], "target": [-9.0, -5.9, 10.0]}`

