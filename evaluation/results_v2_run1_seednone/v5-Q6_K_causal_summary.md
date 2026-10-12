# v5-Q6_K · causal 评测汇总（v2 六指标）

- 模型 `phi2-v5-q6_k.gguf` | n=240 | 2026-10-12 12:42:49 | 显存 4491MB | 耗时 234.4s

## 六指标总览

- 主指标（按 judge 类型）：**54/240 (22.5%, CI [17.7, 28.2])**
- schema 有效率：103/240 (42.9%, CI [36.8, 49.2])
- 非法动作率（schema 合法但包络外）：0/240 (0.0%, CI [0.0, 1.6])
- 延迟 ms：p50=1097 p95=1305 max=1324

## 字段级准确率（有金标准条目）

| 字段 | 准确率 |
|---|---|
| mode | 95/107 (88.8%, CI [81.4, 93.5]) |
| formation | 47/107 (43.9%, CI [34.9, 53.4]) |
| ids | 94/107 (87.9%, CI [80.3, 92.8]) |
| tx | 104/107 (97.2%, CI [92.1, 99.0]) |
| ty | 104/107 (97.2%, CI [92.1, 99.0]) |
| tz | 56/107 (52.3%, CI [43.0, 61.6]) |

- 坐标 MAE-x: 0.720 m (bootstrap 95% CI [0.000, 1.813], n=107)
- 坐标 MAE-y: 0.355 m (bootstrap 95% CI [0.000, 0.841], n=107)
- 坐标 MAE-z: 3.598 m (bootstrap 95% CI [2.804, 4.411], n=107)

## 按类别

| category | n | 主指标 | schema | 非法 |
|---|---|---|---|---|
| G2-situation-prose | 80 | 0/80 (0.0%, CI [0.0, 4.6]) | 0/80 | 0 |
| G3-structured-summary | 80 | 10/80 (12.5%, CI [6.9, 21.5]) | 26/80 | 0 |
| G4-phase-label | 80 | 44/80 (55.0%, CI [44.1, 65.4]) | 77/80 | 0 |

## 失败样例（前 12 / 186）

- **C-001** [G2-situation-prose/ASSEMBLE] unparseable: `UAV swarm control context: 4 followers in line formation, virtual leader holding at (27, -6, 4) head`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 2], "target": [9.0, 4.0, 5.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [9.0, 4.0, 4.0], "mode_uav": "single`
- **C-002** [G3-structured-summary/ASSEMBLE] target-z: `Situation summary: context=swarm control; units=4; rendezvous=(9,4); action=gather; calm; mode=coope`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 2], "target": [9.0, 4.0, 5.0]}；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [1, 2], "target": [9.0, 4.0, 8.0], "uav_ids": [3, 4], "targe`
- **C-003** [G4-phase-label/ASSEMBLE] target-z: `UAV 1 and 2, tighten up.`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 2], "target": [9.0, 4.0, 5.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2], "target": [9.0, 4.0, 1.0]}`
- **C-004** [G2-situation-prose/ASSEMBLE] unparseable: `UAV swarm control context: 4 followers in grid formation, virtual leader holding at (-1, 22, 11) hea`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [1], "target": [-4.0, -3.0, 5.0]}；输出 `{"mode": "swarm", "formation": "grid", "uav_ids": [1, 2, 3, 4], "target": [-4.0, -3.0, 11.0], "mode": "single-`
- **C-005** [G3-structured-summary/ASSEMBLE] unparseable: `Situation summary: context=swarm control; units=4; rendezvous=(-4,-3); action=gather; moderate_wind_`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [1], "target": [-4.0, -3.0, 5.0]}；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [1, 2, 3, 4], "target": [-4.0, -3.0, 0.0], "uav_ids": [1, 2,`
- **C-007** [G2-situation-prose/ASSEMBLE] unparseable: `UAV swarm control context: 4 followers in grid formation, virtual leader holding at (24, 18, 6) head`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [3], "target": [-3.0, -10.0, 5.0]}；输出 `{"mode": "swarm", "formation": "grid", "uav_ids": [1, 2, 3, 4], "target": [-3.0, -10.0, 6.0], "mode": "single-`
- **C-010** [G2-situation-prose/ASSEMBLE] unparseable: `UAV swarm control context: 4 followers in line formation, virtual leader holding at (39, -6, 11) hea`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [3, 4], "target": [10.0, 4.0, 5.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [10.0, 4.0, 11.0], "mode_change": "s`
- **C-011** [G3-structured-summary/ASSEMBLE] unparseable: `Situation summary: context=swarm control; units=4; rendezvous=(10,4); action=gather; fresh_wind_from`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [3, 4], "target": [10.0, 4.0, 5.0]}；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [3, 4], "target": [10.0, 4.0, 8.0], "mode": "single-agent", `
- **C-013** [G2-situation-prose/ASSEMBLE] unparseable: `UAV swarm control context: 4 followers in column formation, virtual leader holding at (32, 20, 6) he`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [1], "target": [2.0, 0.0, 5.0]}；输出 `{"mode": "swarm", "formation": "column", "uav_ids": [1, 2, 3, 4], "target": [32.0, 20.0, 6.0], "mode": "single`
- **C-015** [G4-phase-label/ASSEMBLE] target-z: `UAV 1, continue.`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [1], "target": [2.0, 0.0, 5.0]}；输出 `{"mode": "single-agent", "formation": "free", "uav_ids": [1], "target": [2.0, 0.0, 2.0]}`
- **C-016** [G2-situation-prose/ASSEMBLE] unparseable: `UAV swarm control context: 4 followers in column formation, virtual leader holding at (39, 47, 10) h`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [1], "target": [4.0, 2.0, 5.0]}；输出 `{"mode": "swarm", "formation": "column", "uav_ids": [1, 2, 3, 4], "target": [39.0, 47.0, 10.0], "mode": "singl`
- **C-017** [G3-structured-summary/ASSEMBLE] unparseable: `Situation summary: context=swarm control; units=4; rendezvous=(4,2); action=gather; calm; status=rea`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [1], "target": [4.0, 2.0, 5.0]}；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [1, 2, 3, 4], "target": [4.0, 2.0, 8.0], "uav_ids_mode": "si`

