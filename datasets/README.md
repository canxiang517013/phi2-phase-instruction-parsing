# 训练数据集版本清单（冻结资产，只读）

| 文件 | 条数 | 语义版本 | 说明 |
|---|---|---|---|
| `dataset_original_109.jsonl` | 109 | v0 | 8 月初始，基础 DMPC 指令 |
| `dataset.jsonl` | 287 | v1 | 扩展 + 多机编队 |
| `dataset_phased.jsonl` | 209 | v2 | + 相位前缀 |
| `dataset_phased_v2.jsonl` | 399 | **v3** | 迭代（⚠ 文件名编号与语义版本差一位） |
| `dataset_phased_v3.jsonl` | 233 | **v4** | 迭代 |
| `dataset_phased_v4.jsonl` | 287 | v4 前身 | v5 的直接前身 |
| `dataset_phased_v5.jsonl` | 330 | **v5 ★主力** | 相位条件化解析（训练默认） |
| `dataset_v6.jsonl` | 485 | v6 | z 去指纹实验（失败：mode 偏置 + EOS 退化，勿用） |
| `dataset_v6_3.jsonl` | 485 | v6.3 | v6 修机号 bug 重训版（方案 D7）：v5 全量 330 + v6 保留 139 + 16 条修复样本 |
| `dataset_v6lc.jsonl` | 450 | v6lc | 长上下文版（G7） |
| `g7_long_120.jsonl` | 120 | g7 | G7 增强长态势（v6lc 增量原料） |

训练入口（src/training/）：
```bash
python src/training/train_qlora.py                    # v5 主力 → adapters/dmpc_v5（入库）
PHI2_SMOKE=40 python src/training/train_qlora.py      # 冒烟，产物 adapters/dmpc_v5_smoke，不覆盖正式权重
PHI2_DATA=dataset_v6_3.jsonl PHI2_VER=v6_3 python src/training/train_qlora.py   # 环境变量切换数据集/版本
python src/training/train_qlora_v6lc.py               # v6lc 长上下文
```
