# 规则引擎 vs 云端 LLM 相位推断一致性报告

- 生成时间：2026-09-06 19:07:37
- 态势数：40（explicit=15, implicit=15, ambiguous=5, bilingual=5）
- 对比引擎：deepseek | temperature=0.0 | repeat=3 | timeout=30.0s

## 规则引擎基线（金标准子集）

| 有金标准的态势 | 精确匹配 | 类型匹配 |
|---|---|---|
| 35 | 14 (40%) | 19 (54%) |

## deepseek（deepseek-chat）

| 指标 | 值 |
|---|---|
| 解析漏斗 | 首次成功 120 / 重试后成功 0 / 失败 0 |
| 延迟 ms | mean=563 p50=523 p95=861 max=1446 |
| token | 输入 44025 / 输出 1078（成本估算 ¥0.0913） |
| 与规则引擎一致 | 45/120 (38%) |
| · explicit 一致 | 42/45 (93%) |
| · implicit 一致 | 0/45 (0%) |
| · ambiguous 一致 | 3/15 (20%) |
| · bilingual 一致 | 0/15 (0%) |
| 金标准（n=105） | 精确 100 (95%) / 类型 100 (95%) |
| 确定性（重复运行） | 98%（40 条 × 3 次） |

### 与规则引擎的分歧案例（25 条）

| id | 类别 | 态势 | 规则引擎 | deepseek | 金标准 |
|---|---|---|---|---|---|
| E13 | explicit | Hold position at (3, -2, 7). | `HOLD@(0,0,5)` | `HOLD@(3,-2,7)` | `HOLD@(3,-2,7)` |
| I01 | implicit | Weather radar shows a strong downdraft zone 25 m ahead; lateral detour to the le | `HOLD@(0,0,5)` | `OBSTACLE_AVOID@left@25` | `OBSTACLE_AVOID@left@25` |
| I02 | implicit | A bird flock is crossing the corridor from the right at about 30 m. | `HOLD@(0,0,5)` | `OBSTACLE_AVOID@right@30` | `OBSTACLE_AVOID@right@30` |
| I03 | implicit | Ground fire reported in the sector straight ahead; shift the swarm to the southe | `HOLD@(0,0,5)` | `OBSTACLE_AVOID@left@35` | `OBSTACLE_AVOID@left@35` |
| I04 | implicit | Command requests all units consolidate at checkpoint Bravo (12,-8) for the night | `HOLD@(0,0,5)` | `ASSEMBLE@(12,-8)` | `ASSEMBLE@(12,-8)` |
| I05 | implicit | Mission control wants the swarm pulled back together over landing zone 2 at (-20 | `HOLD@(0,0,5)` | `ASSEMBLE@(-20,15)` | `ASSEMBLE@(-20,15)` |
| I06 | implicit | All aircraft are to close in on the refuel point at (5, 5). | `HOLD@(0,0,5)` | `ASSEMBLE@(5,5)` | `ASSEMBLE@(5,5)` |
| I07 | implicit | We need eyes on the ridge at (140, -60) before dawn. | `HOLD@(0,0,5)` | `RECON@(140,-60)` | `RECON@(140,-60)` |
| I08 | implicit | Sneak a closer look at the compound at (110, 95). | `HOLD@(0,0,5)` | `RECON@(110,95)` | `RECON@(110,95)` |
| I09 | implicit | Send the swarm forward to survey the river bend at (80, 120). | `HOLD@(0,0,5)` | `RECON@(80,120)` | `RECON@(80,120)` |
| I10 | implicit | The canyon ahead is narrow; tighten the column for transit. | `HOLD@(0,0,5)` | `RECONFIGURE@column` | `RECONFIGURE@column` |
| I11 | implicit | For the final approach, switch the group to a staggered wedge. | `HOLD@(0,0,5)` | `RECONFIGURE@wedge` | `RECONFIGURE@wedge` |
| I12 | implicit | Spread into a ring for 360-degree sensor coverage. | `HOLD@(0,0,5)` | `RECONFIGURE@circle` | `RECONFIGURE@circle` |
| I13 | implicit | Enemy air defense is active; all units stay low and keep to current stations (0, | `HOLD@(0,0,5)` | `HOLD@(0,0,3)` | `HOLD@(0,0,3)` |
| I14 | implicit | Fuel margin is thin; minimize movement and maintain current positions (8, 4, 6). | `HOLD@(0,0,5)` | `HOLD@(8,4,6)` | `HOLD@(8,4,6)` |
| I15 | implicit | Nothing new on the battlefield; keep loitering where you are (2, -3, 10). | `HOLD@(0,0,5)` | `HOLD@(2,-3,10)` | `HOLD@(2,-3,10)` |
| A01 | ambiguous | Situation developing fast at grid (60, 40); commander requests presence. | `HOLD@(0,0,5)` | `ASSEMBLE@(60,40)` | `-` |
| A02 | ambiguous | Traffic control reports multiple contacts merging near the swarm. | `HOLD@(0,0,5)` | `OBSTACLE_AVOID@right@30` | `-` |
| A03 | ambiguous | The western task force requests support when able. | `HOLD@(0,0,5)` | `RECON@(120,90)` | `-` |
| A05 | ambiguous | One unit reports a degraded GPS lock. | `HOLD@(0,0,5)` | `RECON@(120,90)` | `-` |
| B01 | bilingual | 所有单位向 B 区靠拢待命，坐标 (15, 20)。 | `HOLD@(0,0,5)` | `ASSEMBLE@(15,20)` | `ASSEMBLE@(15,20)` |
| B02 | bilingual | 前方左侧 30 米出现鸟群，建议向左绕开。 | `HOLD@(0,0,5)` | `OBSTACLE_AVOID@left@30` | `OBSTACLE_AVOID@left@30` |
| B03 | bilingual | 指挥要求抵近 (120, 90) 查明情况。 | `HOLD@(0,0,5)` | `RECON@(120,90)` | `RECON@(120,90)` |
| B04 | bilingual | 即将进入狭窄峡谷，收紧纵队通行。 | `HOLD@(0,0,5)` | `RECONFIGURE@line` | `RECONFIGURE@column` |
| B05 | bilingual | 保持当前阵位 (3, -2, 7) 待命。 | `HOLD@(0,0,5)` | `HOLD@(3,-2,7)` | `HOLD@(3,-2,7)` |

## 说明

- 一致性 = LLM 与规则引擎输出完全相同的比例；分歧本身是研究素材（隐式语义类规则引擎回落 `HOLD@(0,0,5)`，LLM 若给出正确相位即"LLM 必要性"证据）。
- 类型匹配 = 相位名+方向/队形一致、参数容差（如距离 25 vs 30）。
- 成本为估算（PRICES 常量快照），以官网当前价格为准。
