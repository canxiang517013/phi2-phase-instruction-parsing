# v5-Q4_K_M · basic 评测汇总

- 模型: `phi2-v5-q4_k_m.gguf` | n=240 | 2026-09-07 08:54:03
- 显存(加载后总量): 2864MB | 耗时 138.8s

## 总体

- 主指标（basic=精确匹配 / phase=规则容差）：**235/240 (97.9%, CI [95.2, 99.1])**
- JSON 解析失败: 0/240
- 延迟 ms: mean=578 p50=575 max=1843

## 按 split

| split | n | 主指标 |
|---|---|---|
| in | 160 | 157/160 (98.1%, CI [94.6, 99.4]) |
| out | 80 | 78/80 (97.5%, CI [91.3, 99.3]) |

## 按类别

| category | n | 主指标 | subject_ok |
|---|---|---|---|
| single-agent | 90 | 90/90 (100.0%, CI [95.9, 100.0]) | - |
| swarm-circle | 30 | 28/30 (93.3%, CI [78.7, 98.2]) | - |
| swarm-grid | 30 | 29/30 (96.7%, CI [83.3, 99.4]) | - |
| swarm-line | 30 | 28/30 (93.3%, CI [78.7, 98.2]) | - |
| swarm-triangle | 30 | 30/30 (100.0%, CI [88.6, 100.0]) | - |
| swarm-wedge | 30 | 30/30 (100.0%, CI [88.6, 100.0]) | - |

## 失败样例（前 10 / 共 5）

- **B-100** [swarm-line/in] mode: `UAV 1, 2 and 3, line formation, target (6.3, -2.5, 2.1).`
  - 期望 target=[6.3, -2.5, 2.1]；输出 `{"mode": "line", "formation": "free", "uav_ids": [1, 2, 3], "target": [6.3, -2.5, 2.1]}`
- **B-104** [swarm-line/in] mode: `UAV 1 and 5, line formation, target (-28, 29, 22).`
  - 期望 target=[-28.0, 29.0, 22.0]；输出 `{"mode": "line", "formation": "free", "uav_ids": [1, 5], "target": [-28.0, 29.0, 22.0]}`
- **B-157** [swarm-grid/in] mode: `UAV 2, 3 and 5, grid formation, target (-17.3, 2.4, 11.1).`
  - 期望 target=[-17.3, 2.4, 11.1]；输出 `{"mode": "grid", "formation": "free", "uav_ids": [2, 3, 5], "target": [-17.3, 2.4, 11.1]}`
- **B-235** [swarm-circle/out] target: `Have UAV 3 and 4 form up in a circle and proceed to (-13, -59.4, 18).`
  - 期望 target=[-13.0, -59.4, 18.0]；输出 `{"mode": "swarm", "formation": "circle", "uav_ids": [3, 4], "target": [-13.0, -5.0, 18.0]}`
- **B-239** [swarm-circle/out] target: `Have UAV 2, 4 and 5 form up in a circle and proceed to (-9, -59.2, 10).`
  - 期望 target=[-9.0, -59.2, 10.0]；输出 `{"mode": "swarm", "formation": "circle", "uav_ids": [2, 4, 5], "target": [-9.0, -5.8, 10.0]}`

