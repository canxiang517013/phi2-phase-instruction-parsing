# v5q5-smoke · phase 评测汇总

- 模型: `phi2-phased-v5-q5_k_m.gguf` | n=30 | 2026-09-06 20:22:14
- 显存(加载后总量): 3777MB | 耗时 13.3s

## 总体

- 主指标（basic=精确匹配 / phase=规则容差）：**19/30 (63.3%, CI [45.5, 78.1])**
- 次级（指令主体 mode+uav_ids）：30/30 (100.0%, CI [88.6, 100.0])
- JSON 解析失败: 0/30
- 延迟 ms: mean=443 p50=438 max=598

## 按 split

| split | n | 主指标 |
|---|---|---|
| seen | 10 | 7/10 (70.0%, CI [39.7, 89.2]) |
| in-range-unseen | 6 | 5/6 (83.3%, CI [43.6, 97.0]) |
| ood | 10 | 7/10 (70.0%, CI [39.7, 89.2]) |
| in | 4 | 0/4 (0.0%, CI [0.0, 49.0]) |

## 按类别

| category | n | 主指标 | subject_ok |
|---|---|---|---|
| ASSEMBLE | 8 | 7/8 (87.5%, CI [52.9, 97.8]) | 8/8 |
| HOLD | 8 | 8/8 (100.0%, CI [67.6, 100.0]) | 8/8 |
| OBSTACLE_AVOID | 5 | 2/5 (40.0%, CI [11.8, 76.9]) | 5/5 |
| RECON | 5 | 2/5 (40.0%, CI [11.8, 76.9]) | 5/5 |
| RECONFIGURE | 4 | 0/4 (0.0%, CI [0.0, 49.0]) | 4/4 |

## 失败样例（前 10 / 共 11）

- **P-003** [ASSEMBLE/ood] target-z: `All units, change formation.`
  - 期望 target=[-30.0, 8.0, 5.0]；输出 `{"mode": "swarm", "formation": "wedge", "uav_ids": [1, 2, 3, 4], "target": [-30.0, 8.0, 15.0]}`
- **P-008** [OBSTACLE_AVOID/seen] target-z: `UAV 3 and 4, adjust formation.`
  - 期望 target=[20.0, 0.0, 15.0]；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [3, 4], "target": [20.0, 0.0, 5.0]}`
- **P-009** [RECON/in-range-unseen] target-z: `All units, execute.`
  - 期望 target=[142.0, 171.0, 15.0]；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [142.0, 171.0, 5.0]}`
- **P-018** [RECON/seen] target-z: `Everyone, hold.`
  - 期望 target=[200.0, 150.0, 15.0]；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [200.0, 150.0, 5.0]}`
- **P-022** [RECONFIGURE/in] target-y: `Squad, take cover.`
  - 期望 target=[15.0, 15.0, 8.0]；输出 `{"mode": "swarm", "formation": "column", "uav_ids": [1, 2, 3, 4], "target": [15.0, -15.0, 15.0]}`
- **P-024** [RECONFIGURE/in] target-z: `All units, form up.`
  - 期望 target=[15.0, 15.0, 8.0]；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 2, 3, 4], "target": [15.0, 15.0, 15.0]}`
- **P-025** [OBSTACLE_AVOID/ood] target-z: `UAV 1 and 4, adjust formation.`
  - 期望 target=[-10.0, 0.0, 15.0]；输出 `{"mode": "swarm", "formation": "line", "uav_ids": [1, 4], "target": [-10.0, 0.0, 10.0]}`
- **P-026** [RECONFIGURE/in] target-y: `All units, evade.`
  - 期望 target=[15.0, 15.0, 8.0]；输出 `{"mode": "swarm", "formation": "wedge", "uav_ids": [1, 2, 3, 4], "target": [15.0, -15.0, 15.0]}`
- **P-027** [RECON/seen] target-z: `UAV 2 and 3, adjust formation.`
  - 期望 target=[168.0, 195.0, 15.0]；输出 `{"mode": "swarm", "formation": "wedge", "uav_ids": [2, 3], "target": [168.0, 195.0, 5.0]}`
- **P-029** [OBSTACLE_AVOID/ood] target-x: `UAV 2, change position.`
  - 期望 target=[-60.0, 0.0, 15.0]；输出 `{"mode": "single-agent", "formation": "free", "uav_ids": [2], "target": [-15.0, 0.0, 15.0]}`

