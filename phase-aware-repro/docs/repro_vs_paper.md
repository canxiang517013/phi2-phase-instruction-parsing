# 复现 vs 仓库论文结果对比

## baseline（复现 10/10 seeds）

| 指标 | 复现 (mean±std) | 仓库参考 (mean±std) |
|---|---|---|
| first_success_episode | 1262.70 ± 777.41 | 968.70 ± 277.15 (N=10) |
| stable_breakthrough_episode | 1820.40 ± 561.16 | 1676.80 ± 439.67 (N=10) |
| final_acquisition_rate | 90.00 ± 31.62 | 100.00 ± 0.00 (N=10) |
| final_success_rate | 75.20 ± 41.90 | 97.70 ± 4.62 (N=10) |
| final_follow_position_error | 10.11 ± 11.13 | 4.61 ± 1.85 (N=10) |
| final_pairwise_formation_error | 11.64 ± 14.17 | 5.18 ± 3.27 (N=10) |

### baseline per-seed 明细（复现 vs 参考）

| seed | 复现 first_success | 参考 first_success | 复现 final_SR% | 参考 final_SR% |
|---|---|---|---|---|
| 21 | 957 | 1060 | 100.0 | 90.0 |
| 618 | 1071 | 1432 | 100.0 | 99.0 |
| 2024 | 524 | 744 | 100.0 | 100.0 |
| 7 | 976 | 1210 | 96.0 | 88.0 |
| 999 | 2501 | 860 | 0.0 | 100.0 |
| 31415 | 2501 | 1214 | 0.0 | 100.0 |
| 456 | 805 | 895 | 100.0 | 100.0 |
| 789 | 2026 | 935 | 56.0 | 100.0 |
| 555 | 512 | 444 | 100.0 | 100.0 |
| 8888 | 754 | 893 | 100.0 | 100.0 |

## rule_based（复现 10/10 seeds）

| 指标 | 复现 (mean±std) | 仓库参考 (mean±std) |
|---|---|---|
| first_success_episode | 1199.90 ± 629.10 | 884.40 ± 302.49 |
| stable_breakthrough_episode | 1907.60 ± 553.13 | 1684.30 ± 418.99 |
| final_acquisition_rate | 100.00 ± 0.00 | — |
| final_success_rate | 77.40 ± 39.07 | 98.20 ± 3.36 |
| final_follow_position_error | 7.96 ± 5.71 | 4.80 ± 1.91 |
| final_pairwise_formation_error | 9.16 ± 8.20 | 5.27 ± 3.30 |
