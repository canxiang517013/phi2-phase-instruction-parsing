# 工程治理文档（2026-10-15，训练服务器侧产出）

| 文档 | 内容 |
|---|---|
| `01_全量文件梳理.md` | 迁移包资产盘点与问题清单（P1-P10） |
| `02_命名与目录规范.md` | 命名/目录/ROS 规范、版本化资产模式、Red/Blue/Referee 边界条款 |
| `03_目标架构_3v3对抗.md` | 双域架构、模块职责边界、多机异构三层配置 |
| `04_重构执行计划.md` | 迁移清单、依赖修复方案、验证清单（含执行实录） |

> **路径对照说明**：四份文档最初按训练服务器本地的 `llm/` 布局编写；该布局已并入本仓库的
> `src/` 结构（见下方映射）。文档中的**命名规则、版本化策略、边界条款继续有效**，路径按下表换读：
>
> | 文档中的路径 | 本仓库实际位置 |
> |---|---|
> | `llm/phi2_common/` | `src/common/` |
> | `llm/train/` | `src/training/` |
> | `llm/eval/` | `src/evaluation/` |
> | `llm/datasets/` | `datasets/`（保留原文件名） |
> | `llm/testsets/` | `evaluation/testsets/` |
> | `llm/adapters/dmpc_*` | `adapters/dmpc_*` |
> | `ros2_ws/src/*`（设计占位） | `src/nodes/{cloud,edge,referee,tools}` + `launch/`（实现已存在，拓扑为 cloud/edge/referee 三层） |

> **P10 已解决**：迁移包缺失的 `eval_run.py`、`gen_testset.py` 已随远端仓库恢复（`src/evaluation/`）；
> `phase_fault_proxy.py` 对应 `src/nodes/tools/fault_proxy.py`（如需在评测中引用，调整 `run_comm_pilot.py` 的导入路径即可）。
