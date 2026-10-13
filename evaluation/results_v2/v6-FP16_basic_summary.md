# v6-FP16 · basic 评测汇总（v2 六指标）

- 模型 `phi2-v6-fp16.gguf` | n=240 | 2026-10-13 09:19:12 | 显存 6032MB | 耗时 794.4s

## 六指标总览

- 主指标（按 judge 类型）：**149/240 (62.1%, CI [55.8, 68.0])**
- schema 有效率：240/240 (100.0%, CI [98.4, 100.0])
- 非法动作率（schema 合法但包络外）：0/240 (0.0%, CI [0.0, 1.6])
- 延迟 ms：p50=3224 p95=4165 max=6815

## 字段级准确率（有金标准条目）

| 字段 | 准确率 |
|---|---|
| mode | 150/240 (62.5%, CI [56.2, 68.4]) |
| formation | 201/240 (83.8%, CI [78.6, 87.9]) |
| ids | 239/240 (99.6%, CI [97.7, 99.9]) |
| tx | 240/240 (100.0%, CI [98.4, 100.0]) |
| ty | 240/240 (100.0%, CI [98.4, 100.0]) |
| tz | 240/240 (100.0%, CI [98.4, 100.0]) |

- 坐标 MAE-x: 0.000 m (bootstrap 95% CI [0.000, 0.000], n=240)
- 坐标 MAE-y: 0.000 m (bootstrap 95% CI [0.000, 0.000], n=240)
- 坐标 MAE-z: 0.000 m (bootstrap 95% CI [0.000, 0.000], n=240)

## 按类别

| category | n | 主指标 | schema | 非法 |
|---|---|---|---|---|
| single-agent | 90 | 0/90 (0.0%, CI [0.0, 4.1]) | 90/90 | 0 |
| swarm-circle | 30 | 30/30 (100.0%, CI [88.6, 100.0]) | 30/30 | 0 |
| swarm-grid | 30 | 30/30 (100.0%, CI [88.6, 100.0]) | 30/30 | 0 |
| swarm-line | 30 | 30/30 (100.0%, CI [88.6, 100.0]) | 30/30 | 0 |
| swarm-triangle | 30 | 29/30 (96.7%, CI [83.3, 99.4]) | 30/30 | 0 |
| swarm-wedge | 30 | 30/30 (100.0%, CI [88.6, 100.0]) | 30/30 | 0 |

## 失败样例（前 12 / 91）

- **B-001** [single-agent/in] mode: `Drone 5, head to (23, -11, 15).`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [5], "target": [23.0, -11.0, 15.0]}；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [5], "target": [23.0, -11.0, 15.0]}`
- **B-002** [single-agent/in] mode: `UAV 3, travel to (5.4, 28.3, 2.3).`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [3], "target": [5.4, 28.3, 2.3]}；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [3], "target": [5.4, 28.3, 2.3]}`
- **B-003** [single-agent/in] mode: `UAV 1, go to (22, 12, 4).`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [1], "target": [22.0, 12.0, 4.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1], "target": [22.0, 12.0, 4.0]}`
- **B-004** [single-agent/in] mode: `UAV 4, move to (-5.3, -7.3, 2.9).`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [4], "target": [-5.3, -7.3, 2.9]}；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [4], "target": [-5.3, -7.3, 2.9]}`
- **B-005** [single-agent/in] mode: `Drone 2, go to (-14.4, 13.3, 2.4).`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [2], "target": [-14.4, 13.3, 2.4]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [2], "target": [-14.4, 13.3, 2.4]}`
- **B-006** [single-agent/in] mode: `Unit 1, navigate to (15, -19, 14).`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [1], "target": [15.0, -19.0, 14.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1], "target": [15.0, -19.0, 14.0]}`
- **B-007** [single-agent/in] mode: `Drone 4, head to (23.1, 3.1, 24.6).`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [4], "target": [23.1, 3.1, 24.6]}；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [4], "target": [23.1, 3.1, 24.6]}`
- **B-008** [single-agent/in] mode: `UAV 1, travel to (20, -1, 23).`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [1], "target": [20.0, -1.0, 23.0]}；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [1], "target": [20.0, -1.0, 23.0]}`
- **B-009** [single-agent/in] mode: `UAV 3, navigate to (11.8, 20.9, 22).`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [3], "target": [11.8, 20.9, 22.0]}；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [3], "target": [11.8, 20.9, 22.0]}`
- **B-010** [single-agent/in] mode: `Unit 1, go to (-4.6, 5, 22.5).`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [1], "target": [-4.6, 5.0, 22.5]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1], "target": [-4.6, 5.0, 22.5]}`
- **B-011** [single-agent/in] mode: `UAV 1, proceed to (-2.7, 7.4, 18).`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [1], "target": [-2.7, 7.4, 18.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1], "target": [-2.7, 7.4, 18.0]}`
- **B-012** [single-agent/in] mode: `UAV 3, travel to (-19, 15, 16).`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [3], "target": [-19.0, 15.0, 16.0]}；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [3], "target": [-19.0, 15.0, 16.0]}`

