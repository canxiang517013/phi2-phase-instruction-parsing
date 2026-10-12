# v6lc-Q6_K · causal 评测汇总（v2 六指标）

- 模型 `phi2-v6lc-q6_k.gguf` | n=240 | 2026-10-12 13:32:25 | 显存 4893MB | 耗时 163.5s

## 六指标总览

- 主指标（按 judge 类型）：**96/240 (40.0%, CI [34.0, 46.3])**
- schema 有效率：215/240 (89.6%, CI [85.1, 92.8])
- 非法动作率（schema 合法但包络外）：0/240 (0.0%, CI [0.0, 1.6])
- 延迟 ms：p50=670 p95=826 max=1244

## 字段级准确率（有金标准条目）

| 字段 | 准确率 |
|---|---|
| mode | 163/236 (69.1%, CI [62.9, 74.6]) |
| formation | 61/236 (25.8%, CI [20.7, 31.8]) |
| ids | 233/236 (98.7%, CI [96.3, 99.6]) |
| tx | 169/236 (71.6%, CI [65.5, 77.0]) |
| ty | 175/236 (74.2%, CI [68.2, 79.3]) |
| tz | 123/236 (52.1%, CI [45.8, 58.4]) |

- 坐标 MAE-x: 11.150 m (bootstrap 95% CI [7.564, 15.261], n=234)
- 坐标 MAE-y: 8.564 m (bootstrap 95% CI [4.692, 12.906], n=234)
- 坐标 MAE-z: 3.372 m (bootstrap 95% CI [2.829, 3.915], n=234)

## 按类别

| category | n | 主指标 | schema | 非法 |
|---|---|---|---|---|
| G2-situation-prose | 80 | 46/80 (57.5%, CI [46.6, 67.7]) | 65/80 | 0 |
| G3-structured-summary | 80 | 12/80 (15.0%, CI [8.8, 24.4]) | 71/80 | 0 |
| G4-phase-label | 80 | 38/80 (47.5%, CI [36.9, 58.3]) | 79/80 | 0 |

## 失败样例（前 12 / 144）

- **C-001** [G2-situation-prose/ASSEMBLE] target-z: `UAV swarm control context: 4 followers in line formation, virtual leader holding at (27, -6, 4) head`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 2], "target": [9.0, 4.0, 5.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2], "target": [9.0, 4.0, 0.0]}`
- **C-002** [G3-structured-summary/ASSEMBLE] target-y: `Situation summary: context=swarm control; units=4; rendezvous=(9,4); action=gather; calm; mode=coope`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 2], "target": [9.0, 4.0, 5.0]}；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [1, 2], "target": [8.0, 8.0, 5.0]}`
- **C-003** [G4-phase-label/ASSEMBLE] target-z: `UAV 1 and 2, tighten up.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 2], "target": [9.0, 4.0, 5.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2], "target": [9.0, 4.0, 1.0]}`
- **C-004** [G2-situation-prose/ASSEMBLE] target-z: `UAV swarm control context: 4 followers in grid formation, virtual leader holding at (-1, 22, 11) hea`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [1], "target": [-4.0, -3.0, 5.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1], "target": [-4.0, -3.0, 15.0]}`
- **C-005** [G3-structured-summary/ASSEMBLE] target-x: `Situation summary: context=swarm control; units=4; rendezvous=(-4,-3); action=gather; moderate_wind_`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [1], "target": [-4.0, -3.0, 5.0]}；输出 `{"mode": "single-agent", "formation": "free", "uav_ids": [1], "target": [8.0, 8.0, 8.0]}`
- **C-006** [G4-phase-label/ASSEMBLE] target-z: `UAV 1, proceed.`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [1], "target": [-4.0, -3.0, 5.0]}；输出 `{"mode": "single-agent", "formation": "free", "uav_ids": [1], "target": [-4.0, -3.0, 1.0]}`
- **C-008** [G3-structured-summary/ASSEMBLE] target-x: `Situation summary: context=swarm control; units=4; rendezvous=(-3,-10); action=gather; light_breeze_`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [3], "target": [-3.0, -10.0, 5.0]}；输出 `{"mode": "single-agent", "formation": "free", "uav_ids": [3], "target": [8.0, 8.0, 8.0]}`
- **C-010** [G2-situation-prose/ASSEMBLE] target: `UAV swarm control context: 4 followers in line formation, virtual leader holding at (39, -6, 11) hea`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [3, 4], "target": [10.0, 4.0, 5.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [3, 4], "target": [10.0, 4.0]}`
- **C-011** [G3-structured-summary/ASSEMBLE] target-x: `Situation summary: context=swarm control; units=4; rendezvous=(10,4); action=gather; fresh_wind_from`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [3, 4], "target": [10.0, 4.0, 5.0]}；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [3, 4], "target": [8.0, 8.0, 8.0]}`
- **C-013** [G2-situation-prose/ASSEMBLE] target-z: `UAV swarm control context: 4 followers in column formation, virtual leader holding at (32, 20, 6) he`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [1], "target": [2.0, 0.0, 5.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1], "target": [2.0, 0.0, 0.0]}`
- **C-015** [G4-phase-label/ASSEMBLE] target-z: `UAV 1, continue.`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [1], "target": [2.0, 0.0, 5.0]}；输出 `{"mode": "single-agent", "formation": "free", "uav_ids": [1], "target": [2.0, 0.0, 0.0]}`
- **C-016** [G2-situation-prose/ASSEMBLE] target-z: `UAV swarm control context: 4 followers in column formation, virtual leader holding at (39, 47, 10) h`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [1], "target": [4.0, 2.0, 5.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1], "target": [4.0, 2.0, 2.0]}`

