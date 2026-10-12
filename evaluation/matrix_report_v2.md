# P0-2 评估体系 v2 · 全量矩阵报告

生成：2026-10-12 12:21 | RTX 3060 Laptop 6GB | llama.cpp CUDA | temp=0.1 max_tokens=70 | 测试集 basic_240 + phase_200 + robust_160 = 600 条/档

配对参考档：v5-Q8_0（9 月矩阵结论：Q8_0 逐层量化误差最小，作为能力上界代理；FP16 全量另列）。McNemar 精确二项检验。

## basic

| 档位 | 主指标% [CI] | schema% | 非法动作% | MAE-L2 m | p50 ms | p95 ms |
|---|---|---|---|---|---|---|
| FP16 | 100.0 [98,100] | 100.0 [98,100] | 0.0 [0,2] | 0.00 (n=240) | 2253 | 2467 |
| Q8_0 | 100.0 [98,100] | 100.0 [98,100] | 0.0 [0,2] | 0.00 (n=240) | 548 | 580 |
| Q6_K | 100.0 [98,100] | 100.0 [98,100] | 0.0 [0,2] | 0.00 (n=240) | 591 | 667 |
| Q5_K_M | 97.5 [95,99] | 98.3 [96,99] | 0.0 [0,2] | 0.45 (n=240) | 519 | 549 |
| Q4_K_M | 97.9 [95,99] | 98.8 [96,100] | 0.0 [0,2] | 0.45 (n=240) | 485 | 517 |

配对检验（vs v5-Q8_0，同条目）：
  - v5-FP16: 240/240 vs REF 240/240 | 仅本档对 0 / 仅REF对 0 | p=1.0000
  - v5-Q6_K: 240/240 vs REF 240/240 | 仅本档对 0 / 仅REF对 0 | p=1.0000
  - v5-Q5_K_M: 234/240 vs REF 240/240 | 仅本档对 0 / 仅REF对 6 | p=0.0312 **显著**
  - v5-Q4_K_M: 235/240 vs REF 240/240 | 仅本档对 0 / 仅REF对 5 | p=0.0625

## phase

| 档位 | 主指标% [CI] | schema% | 非法动作% | MAE-L2 m | p50 ms | p95 ms |
|---|---|---|---|---|---|---|
| FP16 | 52.5 [46,59] | 96.5 [93,98] | 0.5 [0,3] | 4.34 (n=198) | 2155 | 2334 |
| Q8_0 | 57.5 [51,64] | 96.0 [92,98] | 0.0 [0,2] | 3.48 (n=196) | 538 | 591 |
| Q6_K | 54.0 [47,61] | 96.0 [92,98] | 0.5 [0,3] | 3.86 (n=195) | 630 | 699 |
| Q5_K_M | 52.5 [46,59] | 97.0 [94,99] | 0.5 [0,3] | 4.49 (n=199) | 534 | 578 |
| Q4_K_M | 43.0 [36,50] | 97.5 [94,99] | 0.0 [0,2] | 5.97 (n=200) | 492 | 540 |

配对检验（vs v5-Q8_0，同条目）：
  - v5-FP16: 105/200 vs REF 115/200 | 仅本档对 7 / 仅REF对 17 | p=0.0639
  - v5-Q6_K: 108/200 vs REF 115/200 | 仅本档对 5 / 仅REF对 12 | p=0.1435
  - v5-Q5_K_M: 105/200 vs REF 115/200 | 仅本档对 17 / 仅REF对 27 | p=0.1742
  - v5-Q4_K_M: 86/200 vs REF 115/200 | 仅本档对 6 / 仅REF对 35 | p=0.0000 **显著**

## robust

| 档位 | 主指标% [CI] | schema% | 非法动作% | MAE-L2 m | p50 ms | p95 ms |
|---|---|---|---|---|---|---|
| FP16 | 13.8 [9,20] | 84.4 [78,89] | 15.6 [11,22] | 88.18 (n=44) | 2174 | 3733 |
| Q8_0 | 13.8 [9,20] | 82.5 [76,88] | 15.6 [11,22] | 60.75 (n=37) | 538 | 918 |
| Q6_K | 15.0 [10,21] | 88.1 [82,92] | 15.0 [10,21] | 80.98 (n=47) | 600 | 1006 |
| Q5_K_M | 14.4 [10,21] | 82.5 [76,88] | 14.4 [10,21] | 69.84 (n=45) | 515 | 871 |
| Q4_K_M | 10.6 [7,16] | 81.2 [74,87] | 13.1 [9,19] | 12.69 (n=31) | 501 | 852 |

配对检验（vs v5-Q8_0，同条目）：
  - v5-FP16: 22/160 vs REF 22/160 | 仅本档对 4 / 仅REF对 4 | p=1.0000
  - v5-Q6_K: 24/160 vs REF 22/160 | 仅本档对 5 / 仅REF对 3 | p=0.7266
  - v5-Q5_K_M: 23/160 vs REF 22/160 | 仅本档对 8 / 仅REF对 7 | p=1.0000
  - v5-Q4_K_M: 17/160 vs REF 22/160 | 仅本档对 6 / 仅REF对 11 | p=0.3323

## 鲁棒性行为分布（robust_160，safe 条目）

| 档位 | bad-phase | missing-field | ambiguous | out-of-envelope |
|---|---|---|---|---|
| FP16 | graceful=2/fabricated=23/dangerous=0 | fabricated=25/dangerous=0 | graceful=1/fabricated=24/dangerous=0 | dangerous=25 |
| Q8_0 | graceful=1/fabricated=24/dangerous=0 | fabricated=25/dangerous=0 | graceful=2/fabricated=23/dangerous=0 | dangerous=25 |
| Q6_K | graceful=2/fabricated=23/dangerous=0 | fabricated=25/dangerous=0 | fabricated=25/dangerous=0 | not=1/dangerous=24 |
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
| Q5_K_M | mode=4, target=2 |
| Q4_K_M | mode=3, target=2 |

### phase

| 档位 | 失败原因分布 |
|---|---|
| FP16 | target-z=88, target-y=4, target=2, target-x=1 |
| Q8_0 | target-z=79, target=4, target-y=1, target-x=1 |
| Q6_K | target-z=85, target=5, target-x=2 |
| Q5_K_M | target-z=89, target-y=3, target-x=2, target=1 |
| Q4_K_M | target-z=104, target-y=6, target-x=4 |

