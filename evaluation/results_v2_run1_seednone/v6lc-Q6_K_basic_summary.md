# v6lc-Q6_K · basic 评测汇总（v2 六指标）

- 模型 `phi2-v6lc-q6_k.gguf` | n=240 | 2026-10-12 13:24:57 | 显存 4804MB | 耗时 145.7s

## 六指标总览

- 主指标（按 judge 类型）：**199/240 (82.9%, CI [77.6, 87.2])**
- schema 有效率：240/240 (100.0%, CI [98.4, 100.0])
- 非法动作率（schema 合法但包络外）：0/240 (0.0%, CI [0.0, 1.6])
- 延迟 ms：p50=611 p95=662 max=690

## 字段级准确率（有金标准条目）

| 字段 | 准确率 |
|---|---|
| mode | 199/240 (82.9%, CI [77.6, 87.2]) |
| formation | 231/240 (96.2%, CI [93.0, 98.0]) |
| ids | 240/240 (100.0%, CI [98.4, 100.0]) |
| tx | 240/240 (100.0%, CI [98.4, 100.0]) |
| ty | 240/240 (100.0%, CI [98.4, 100.0]) |
| tz | 240/240 (100.0%, CI [98.4, 100.0]) |

- 坐标 MAE-x: 0.000 m (bootstrap 95% CI [0.000, 0.000], n=240)
- 坐标 MAE-y: 0.000 m (bootstrap 95% CI [0.000, 0.000], n=240)
- 坐标 MAE-z: 0.000 m (bootstrap 95% CI [0.000, 0.000], n=240)

## 按类别

| category | n | 主指标 | schema | 非法 |
|---|---|---|---|---|
| single-agent | 90 | 81/90 (90.0%, CI [82.1, 94.6]) | 90/90 | 0 |
| swarm-circle | 30 | 25/30 (83.3%, CI [66.4, 92.7]) | 30/30 | 0 |
| swarm-grid | 30 | 17/30 (56.7%, CI [39.2, 72.6]) | 30/30 | 0 |
| swarm-line | 30 | 20/30 (66.7%, CI [48.8, 80.8]) | 30/30 | 0 |
| swarm-triangle | 30 | 28/30 (93.3%, CI [78.7, 98.2]) | 30/30 | 0 |
| swarm-wedge | 30 | 28/30 (93.3%, CI [78.7, 98.2]) | 30/30 | 0 |

## 失败样例（前 12 / 41）

- **B-009** [single-agent/in] mode: `UAV 3, navigate to (11.8, 20.9, 22).`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [3], "target": [11.8, 20.9, 22.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [3], "target": [11.8, 20.9, 22.0]}`
- **B-010** [single-agent/in] mode: `Unit 1, go to (-4.6, 5, 22.5).`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [1], "target": [-4.6, 5.0, 22.5]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1], "target": [-4.6, 5.0, 22.5]}`
- **B-029** [single-agent/in] mode: `UAV 4, navigate to (-21.9, -8.9, 1.6).`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [4], "target": [-21.9, -8.9, 1.6]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [4], "target": [-21.9, -8.9, 1.6]}`
- **B-048** [single-agent/in] mode: `Unit 5, go to (-6.6, 28.2, 12.3).`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [5], "target": [-6.6, 28.2, 12.3]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [5], "target": [-6.6, 28.2, 12.3]}`
- **B-060** [single-agent/in] mode: `Unit 2, travel to (25, -10, 22).`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [2], "target": [25.0, -10.0, 22.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [2], "target": [25.0, -10.0, 22.0]}`
- **B-062** [single-agent/out] mode: `Unit 1, navigate to (-29, 34.7, 13).`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [1], "target": [-29.0, 34.7, 13.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1], "target": [-29.0, 34.7, 13.0]}`
- **B-063** [single-agent/out] mode: `Unit 2, fly to (-38.8, -25.5, 1.4).`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [2], "target": [-38.8, -25.5, 1.4]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [2], "target": [-38.8, -25.5, 1.4]}`
- **B-073** [single-agent/out] mode: `Unit 5, move to (27, -44, 4.5).`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [5], "target": [27.0, -44.0, 4.5]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [5], "target": [27.0, -44.0, 4.5]}`
- **B-087** [single-agent/out] mode: `Unit 4, fly to (-23.1, 3.9, 38.3).`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [4], "target": [-23.1, 3.9, 38.3]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [4], "target": [-23.1, 3.9, 38.3]}`
- **B-091** [swarm-line/in] mode: `UAV 1 and 2, form a line formation and move to target coordinates (-0.7, -10.1, 11.8).`
  - 期望 {"mode": "swarm", "formation": "line", "uav_ids": [1, 2], "target": [-0.7, -10.1, 11.8]}；输出 `{"mode": "single-agent", "formation": "line", "uav_ids": [1, 2], "target": [-0.7, -10.1, 11.8]}`
- **B-093** [swarm-line/in] mode: `UAV 1 and 4, line formation, target (-9, -23, 1).`
  - 期望 {"mode": "swarm", "formation": "line", "uav_ids": [1, 4], "target": [-9.0, -23.0, 1.0]}；输出 `{"mode": "single-agent", "formation": "line", "uav_ids": [1, 4], "target": [-9.0, -23.0, 1.0]}`
- **B-095** [swarm-line/in] mode: `Drones 2 and 5, create a line formation going to (28, -19, 12).`
  - 期望 {"mode": "swarm", "formation": "line", "uav_ids": [2, 5], "target": [28.0, -19.0, 12.0]}；输出 `{"mode": "single-agent", "formation": "line", "uav_ids": [2, 5], "target": [28.0, -19.0, 12.0]}`

