# v5-Q8_0 · causal 评测汇总（v2 六指标）

- 模型 `phi2-v5-q8_0.gguf` | n=240 | 2026-10-12 12:38:52 | 显存 5264MB | 耗时 192.3s

## 六指标总览

- 主指标（按 judge 类型）：**53/240 (22.1%, CI [17.3, 27.7])**
- schema 有效率：97/240 (40.4%, CI [34.4, 46.7])
- 非法动作率（schema 合法但包络外）：0/240 (0.0%, CI [0.0, 1.6])
- 延迟 ms：p50=890 p95=1034 max=1075

## 字段级准确率（有金标准条目）

| 字段 | 准确率 |
|---|---|
| mode | 93/99 (93.9%, CI [87.4, 97.2]) |
| formation | 40/99 (40.4%, CI [31.3, 50.3]) |
| ids | 86/99 (86.9%, CI [78.8, 92.2]) |
| tx | 95/99 (96.0%, CI [90.1, 98.4]) |
| ty | 96/99 (97.0%, CI [91.5, 99.0]) |
| tz | 55/99 (55.6%, CI [45.7, 65.0]) |

- 坐标 MAE-x: 1.505 m (bootstrap 95% CI [0.101, 3.556], n=99)
- 坐标 MAE-y: 0.313 m (bootstrap 95% CI [0.000, 0.707], n=99)
- 坐标 MAE-z: 3.434 m (bootstrap 95% CI [2.626, 4.293], n=99)

## 按类别

| category | n | 主指标 | schema | 非法 |
|---|---|---|---|---|
| G2-situation-prose | 80 | 0/80 (0.0%, CI [0.0, 4.6]) | 0/80 | 0 |
| G3-structured-summary | 80 | 7/80 (8.8%, CI [4.3, 17.0]) | 18/80 | 0 |
| G4-phase-label | 80 | 46/80 (57.5%, CI [46.6, 67.7]) | 79/80 | 0 |

## 失败样例（前 12 / 187）

- **C-001** [G2-situation-prose/ASSEMBLE] unparseable: `UAV swarm control context: 4 followers in line formation, virtual leader holding at (27, -6, 4) head`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [1, 2], "target": [9.0, 4.0, 5.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [9.0, 4.0, 4.0], "mode_change": "swa`
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
- **C-008** [G3-structured-summary/ASSEMBLE] unparseable: `Situation summary: context=swarm control; units=4; rendezvous=(-3,-10); action=gather; light_breeze_`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [3], "target": [-3.0, -10.0, 5.0]}；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [3], "target": [-3.0, -10.0, 5.0], "uav_ids": [3, 4, 5, 6], `
- **C-010** [G2-situation-prose/ASSEMBLE] unparseable: `UAV swarm control context: 4 followers in line formation, virtual leader holding at (39, -6, 11) hea`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [3, 4], "target": [10.0, 4.0, 5.0]}；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [10.0, 4.0, 11.0], "mode_change": "s`
- **C-011** [G3-structured-summary/ASSEMBLE] unparseable: `Situation summary: context=swarm control; units=4; rendezvous=(10,4); action=gather; fresh_wind_from`
  - 期望 {"mode": "swarm", "formation": null, "uav_ids": [3, 4], "target": [10.0, 4.0, 5.0]}；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [3, 4], "target": [10.0, 4.0, 8.0], "uav_ids": [3, 4], "mode`
- **C-013** [G2-situation-prose/ASSEMBLE] unparseable: `UAV swarm control context: 4 followers in column formation, virtual leader holding at (32, 20, 6) he`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [1], "target": [2.0, 0.0, 5.0]}；输出 `{"mode": "swarm", "formation": "column", "uav_ids": [1, 2, 3, 4], "target": [32.0, 20.0, 6.0], "mode": "single`
- **C-016** [G2-situation-prose/ASSEMBLE] unparseable: `UAV swarm control context: 4 followers in column formation, virtual leader holding at (39, 47, 10) h`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [1], "target": [4.0, 2.0, 5.0]}；输出 `{"mode": "swarm", "formation": "column", "uav_ids": [1, 2, 3, 4], "target": [39.0, 47.0, 10.0], "mode": "singl`
- **C-017** [G3-structured-summary/ASSEMBLE] unparseable: `Situation summary: context=swarm control; units=4; rendezvous=(4,2); action=gather; calm; status=rea`
  - 期望 {"mode": "single-agent", "formation": "free", "uav_ids": [1], "target": [4.0, 2.0, 5.0]}；输出 `{"mode": "swarm", "formation": "free", "uav_ids": [1, 2, 3, 4], "target": [4.0, 2.0, 8.0], "mode": "single-age`

