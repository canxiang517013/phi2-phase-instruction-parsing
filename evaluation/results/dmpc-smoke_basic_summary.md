# dmpc-smoke · basic 评测汇总

- 模型: `dmpc-q6_k.gguf` | n=20 | 2026-09-06 20:26:51
- 显存(加载后总量): 4551MB | 耗时 9.6s

## 总体

- 主指标（basic=精确匹配 / phase=规则容差）：**0/20 (0.0%, CI [0.0, 16.1])**
- JSON 解析失败: 0/20
- 延迟 ms: mean=481 p50=470 max=646

## 按 split

| split | n | 主指标 |
|---|---|---|
| in | 20 | 0/20 (0.0%, CI [0.0, 16.1]) |

## 按类别

| category | n | 主指标 | subject_ok |
|---|---|---|---|
| single-agent | 20 | 0/20 (0.0%, CI [0.0, 16.1]) | - |

## 失败样例（前 10 / 共 20）

- **B-001** [single-agent/in] mode: `Drone 5, head to (23, -11, 15).`
  - 期望 target=[23.0, -11.0, 15.0]；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [5], "target": [23.0, -11.0, 15.0]}`
- **B-002** [single-agent/in] mode: `UAV 3, travel to (5.4, 28.3, 2.3).`
  - 期望 target=[5.4, 28.3, 2.3]；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [3], "target": [5.4, 28.3, 2.3]}`
- **B-003** [single-agent/in] mode: `UAV 1, go to (22, 12, 4).`
  - 期望 target=[22.0, 12.0, 4.0]；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [1], "target": [22.0, 12.0, 4.0]}`
- **B-004** [single-agent/in] mode: `UAV 4, move to (-5.3, -7.3, 2.9).`
  - 期望 target=[-5.3, -7.3, 2.9]；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [4], "target": [-5.3, -7.3, 2.9]}`
- **B-005** [single-agent/in] mode: `Drone 2, go to (-14.4, 13.3, 2.4).`
  - 期望 target=[-14.4, 13.3, 2.4]；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [2], "target": [-14.4, 13.3, 2.4]}`
- **B-006** [single-agent/in] mode: `Unit 1, navigate to (15, -19, 14).`
  - 期望 target=[15.0, -19.0, 14.0]；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [1], "target": [15.0, -19.0, 14.0]}`
- **B-007** [single-agent/in] mode: `Drone 4, head to (23.1, 3.1, 24.6).`
  - 期望 target=[23.1, 3.1, 24.6]；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [4], "target": [23.1, 3.1, 24.6]}`
- **B-008** [single-agent/in] mode: `UAV 1, travel to (20, -1, 23).`
  - 期望 target=[20.0, -1.0, 23.0]；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [1], "target": [20.0, -1.0, 23.0]}`
- **B-009** [single-agent/in] mode: `UAV 3, navigate to (11.8, 20.9, 22).`
  - 期望 target=[11.8, 20.9, 22.0]；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [3], "target": [11.8, 20.9, 22.0]}`
- **B-010** [single-agent/in] mode: `Unit 1, go to (-4.6, 5, 22.5).`
  - 期望 target=[-4.6, 5.0, 22.5]；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [1], "target": [-4.6, 5.0, 22.5]}`

