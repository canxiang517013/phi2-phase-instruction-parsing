# v5-Q5_K_M · basic 评测汇总

- 模型: `phi2-phased-v5-q5_k_m.gguf` | n=240 | 2026-09-07 08:49:28
- 显存(加载后总量): 3098MB | 耗时 156.5s

## 总体

- 主指标（basic=精确匹配 / phase=规则容差）：**234/240 (97.5%, CI [94.7, 98.8])**
- JSON 解析失败: 0/240
- 延迟 ms: mean=652 p50=606 max=2145

## 按 split

| split | n | 主指标 |
|---|---|---|
| in | 160 | 157/160 (98.1%, CI [94.6, 99.4]) |
| out | 80 | 77/80 (96.2%, CI [89.5, 98.7]) |

## 按类别

| category | n | 主指标 | subject_ok |
|---|---|---|---|
| single-agent | 90 | 90/90 (100.0%, CI [95.9, 100.0]) | - |
| swarm-circle | 30 | 28/30 (93.3%, CI [78.7, 98.2]) | - |
| swarm-grid | 30 | 28/30 (93.3%, CI [78.7, 98.2]) | - |
| swarm-line | 30 | 28/30 (93.3%, CI [78.7, 98.2]) | - |
| swarm-triangle | 30 | 30/30 (100.0%, CI [88.6, 100.0]) | - |
| swarm-wedge | 30 | 30/30 (100.0%, CI [88.6, 100.0]) | - |

## 失败样例（前 10 / 共 6）

- **B-100** [swarm-line/in] mode: `UAV 1, 2 and 3, line formation, target (6.3, -2.5, 2.1).`
  - 期望 target=[6.3, -2.5, 2.1]；输出 `{"mode": "line", "formation": "line", "uav_ids": [1, 2, 3], "target": [6.3, -2.5, 2.1]}`
- **B-109** [swarm-line/in] mode: `UAV 1, 3 and 5, line formation, target (-11.6, -15.1, 4.5).`
  - 期望 target=[-11.6, -15.1, 4.5]；输出 `{"mode": "line", "formation": "free", "uav_ids": [1, 3, 5], "target": [-11.6, -15.1, 4.5]}`
- **B-157** [swarm-grid/in] mode: `UAV 2, 3 and 5, grid formation, target (-17.3, 2.4, 11.1).`
  - 期望 target=[-17.3, 2.4, 11.1]；输出 `{"mode": "grid", "formation": "free", "uav_ids": [2, 3, 5], "target": [-17.3, 2.4, 11.1]}`
- **B-179** [swarm-grid/out] mode: `UAV 2 and 3, grid formation, target (-45.9, 4.1, 4.4).`
  - 期望 target=[-45.9, 4.1, 4.4]；输出 `{"mode": "grid", "formation": "free", "uav_ids": [2, 3], "target": [-45.9, 4.1, 4.4]}`
- **B-235** [swarm-circle/out] target: `Have UAV 3 and 4 form up in a circle and proceed to (-13, -59.4, 18).`
  - 期望 target=[-13.0, -59.4, 18.0]；输出 `{"mode": "swarm", "formation": "circle", "uav_ids": [3, 4], "target": [-13.0, -5.0, 18.0]}`
- **B-239** [swarm-circle/out] target: `Have UAV 2, 4 and 5 form up in a circle and proceed to (-9, -59.2, 10).`
  - 期望 target=[-9.0, -59.2, 10.0]；输出 `{"mode": "swarm", "formation": "circle", "uav_ids": [2, 4, 5], "target": [-9.0, -5.9, 10.0]}`

