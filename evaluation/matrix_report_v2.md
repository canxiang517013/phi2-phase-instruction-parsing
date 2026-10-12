# P0-2 评估体系 v2 · 全量矩阵报告

生成：2026-10-12 21:56 | RTX 3060 Laptop 6GB | llama.cpp CUDA | temp=0.1 max_tokens=70 | 测试集 basic_240 + phase_200 + robust_160 = 600 条/档

配对参考档：v5-Q8_0（9 月矩阵结论：Q8_0 逐层量化误差最小，作为能力上界代理；FP16 全量另列）。McNemar 精确二项检验。

## basic

| 档位 | 主指标% [CI] | schema% | 非法动作% | MAE-L2 m | p50 ms | p95 ms |
|---|---|---|---|---|---|---|
| FP16 | 100.0 [98,100] | 100.0 [98,100] | 0.0 [0,2] | 0.00 (n=240) | 4008 | 22639 |
| Q8_0 | 100.0 [98,100] | 100.0 [98,100] | 0.0 [0,2] | 0.00 (n=240) | 614 | 1585 |
| Q6_K | 100.0 [98,100] | 100.0 [98,100] | 0.0 [0,2] | 0.00 (n=240) | 707 | 2075 |
| Q5_K_M | 99.2 [97,100] | 99.6 [98,100] | 0.0 [0,2] | 0.22 (n=240) | 643 | 708 |
| Q4_K_M | 97.9 [95,99] | 98.8 [96,100] | 0.0 [0,2] | 0.45 (n=240) | 610 | 659 |

配对检验（vs v5-Q8_0，同条目）：
  - v5-FP16: 240/240 vs REF 240/240 | 仅本档对 0 / 仅REF对 0 | p=1.0000
  - v5-Q6_K: 240/240 vs REF 240/240 | 仅本档对 0 / 仅REF对 0 | p=1.0000
  - v5-Q5_K_M: 238/240 vs REF 240/240 | 仅本档对 0 / 仅REF对 2 | p=0.5000
  - v5-Q4_K_M: 235/240 vs REF 240/240 | 仅本档对 0 / 仅REF对 5 | p=0.0625

## phase

| 档位 | 主指标% [CI] | schema% | 非法动作% | MAE-L2 m | p50 ms | p95 ms |
|---|---|---|---|---|---|---|
| FP16 | 53.0 [46,60] | 97.0 [94,99] | 1.0 [0,4] | 4.48 (n=198) | 3306 | 3803 |
| Q8_0 | 58.0 [51,65] | 96.0 [92,98] | 0.0 [0,2] | 3.45 (n=196) | 641 | 1665 |
| Q6_K | 52.5 [46,59] | 95.5 [92,98] | 1.0 [0,4] | 4.29 (n=195) | 759 | 2498 |
| Q5_K_M | 50.5 [44,57] | 97.5 [94,99] | 1.0 [0,4] | 4.74 (n=199) | 659 | 735 |
| Q4_K_M | 41.5 [35,48] | 97.0 [94,99] | 0.0 [0,2] | 5.53 (n=200) | 635 | 697 |

配对检验（vs v5-Q8_0，同条目）：
  - v5-FP16: 106/200 vs REF 116/200 | 仅本档对 5 / 仅REF对 15 | p=0.0414 **显著**
  - v5-Q6_K: 105/200 vs REF 116/200 | 仅本档对 4 / 仅REF对 15 | p=0.0192 **显著**
  - v5-Q5_K_M: 101/200 vs REF 116/200 | 仅本档对 11 / 仅REF对 26 | p=0.0201 **显著**
  - v5-Q4_K_M: 83/200 vs REF 116/200 | 仅本档对 5 / 仅REF对 38 | p=0.0000 **显著**

## robust

| 档位 | 主指标% [CI] | schema% | 非法动作% | MAE-L2 m | p50 ms | p95 ms |
|---|---|---|---|---|---|---|
| FP16 | 13.8 [9,20] | 81.9 [75,87] | 15.0 [10,21] | 76.44 (n=43) | 3325 | 5960 |
| Q8_0 | 13.8 [9,20] | 81.9 [75,87] | 15.6 [11,22] | 65.25 (n=38) | 652 | 1719 |
| Q6_K | 13.1 [9,19] | 87.5 [81,92] | 14.4 [10,21] | 90.51 (n=48) | 734 | 2608 |
| Q5_K_M | 13.1 [9,19] | 82.5 [76,88] | 14.4 [10,21] | 70.39 (n=45) | 658 | 1138 |
| Q4_K_M | 9.4 [6,15] | 80.6 [74,86] | 13.1 [9,19] | 18.97 (n=30) | 656 | 1148 |

配对检验（vs v5-Q8_0，同条目）：
  - v5-FP16: 22/160 vs REF 22/160 | 仅本档对 3 / 仅REF对 3 | p=1.0000
  - v5-Q6_K: 21/160 vs REF 22/160 | 仅本档对 5 / 仅REF对 6 | p=1.0000
  - v5-Q5_K_M: 21/160 vs REF 22/160 | 仅本档对 7 / 仅REF对 8 | p=1.0000
  - v5-Q4_K_M: 15/160 vs REF 22/160 | 仅本档对 5 / 仅REF对 12 | p=0.1435

## 鲁棒性行为分布（robust_160，safe 条目）

| 档位 | bad-phase | missing-field | ambiguous | out-of-envelope |
|---|---|---|---|---|
| FP16 | graceful=2/fabricated=23/dangerous=0 | fabricated=25/dangerous=0 | graceful=3/fabricated=22/dangerous=0 | not=1/dangerous=24 |
| Q8_0 | graceful=1/fabricated=24/dangerous=0 | fabricated=25/dangerous=0 | graceful=3/fabricated=22/dangerous=0 | dangerous=25 |
| Q6_K | graceful=2/fabricated=23/dangerous=0 | fabricated=25/dangerous=0 | fabricated=25/dangerous=0 | not=2/dangerous=23 |
| Q5_K_M | graceful=4/fabricated=21/dangerous=0 | fabricated=25/dangerous=0 | fabricated=25/dangerous=0 | not=2/dangerous=23 |
| Q4_K_M | fabricated=25/dangerous=0 | fabricated=25/dangerous=0 | graceful=1/fabricated=24/dangerous=0 | not=4/dangerous=21 |

（graceful=无可执行输出；fab=捏造但在包络内；not-echoed=越界指令未回声；dangerous=包络外可执行）

## 错误类型分布（有金标准条目的失败原因）

### basic

| 档位 | 失败原因分布 |
|---|---|
| FP16 | （无失败） |
| Q8_0 | （无失败） |
| Q6_K | （无失败） |
| Q5_K_M | mode=1, target=1 |
| Q4_K_M | mode=3, target=2 |

### phase

| 档位 | 失败原因分布 |
|---|---|
| FP16 | target-z=87, target-y=4, target=2, target-x=1 |
| Q8_0 | target-z=78, target=4, target-y=1, target-x=1 |
| Q6_K | target-z=87, target=5, target-x=3 |
| Q5_K_M | target-z=95, target-x=2, target-y=1, target=1 |
| Q4_K_M | target-z=110, target-y=5, target-x=2 |

