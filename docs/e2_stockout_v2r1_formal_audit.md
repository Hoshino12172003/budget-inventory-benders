# E2 V2R1 正式结果归档与验收审计

## 结论

V2R1 的 16 个 `case-policy` 任务通过只读验收。每个任务均包含冻结顺序下的 4,657 个共同需求情景、632 个产品局部块，所有情景状态均为 `OPTIMAL`，且评价前后的一阶段坐标哈希不变。验收脚本没有导入 Gurobi、没有调用 runner，也没有产生新的优化求解。

本结论仅适用于 `experiments/results/e2_stockout_common_scenario_formal_v2r1/`。V1、V2 的部分结果未被并入或改写为 V2R1 证据。

## 冻结对象与口径

- 案例：`210129, 210202, 210310, 210323, 210330, 210428, 210611, 210628`。
- 独立政策：`EXISTING_CANONICAL_<case>` 与 `ROBUST_EQUIVALENT_SCAL_BASE_<case>`。
- Nominal：与 Existing 坐标完全相同的验证标签，不重复计为第三种配置；历史 E2 Nominal 坐标仍未恢复。
- Robust lineage：后续 `SERVICE_CALIBRATION_ROBUSTNESS_V2/SCAL_BASE` 的 `CERTIFIED_PRB_EXACT` 数值等价解，不宣称为原始 E1/E2 坐标。
- 不确定集合：96 个区域—产品需求分量，`Gamma=2`，按冻结 manifest 枚举 4,657 个情景。
- 求解环境记录：Gurobi `13.0.1`，`Threads=1`。

授权文件记录 `formal_run_authorized=true` 是已完成 V2R1 正式运行的历史授权事实。本次归档工作没有修改该记录，也没有再次启动正式运行。

## 只读验收方法

`scripts/audit_e2_stockout_v2r1_archive.py` 独立读取授权、政策身份、共同情景 manifest 和 checkpoint。它逐项执行以下检查：

1. 16 个授权任务及其 checkpoint、SHA-256 sidecar 均存在；
2. 情景 ID 必须严格等于按顺序排列的 `S0000`–`S4656`，不以行数替代集合校验；
3. checkpoint 中的 authorization、identity、scenario、runner、evaluator、instance 和 policy 身份与冻结记录一致；
4. 所有场景均为 `OPTIMAL`，必需指标存在且为有限数；
5. `transportation_cost + shortage_penalty_cost + service_penalty_cost = recourse_cost` 在 `1e-6` 内成立；
6. 评价前后政策坐标哈希均等于授权政策哈希；
7. 名义情景以及总缺货、服务超限、缺货惩罚和经济追索四类最坏值均从 4,657 行重新计算，并核对代表情景及并列信息；
8. numerical fallback 事件字段完整、报告来源为 `ECONOMIC_STAGE`，且原始约束最大违反量不超过冻结容差。

验收读取真实 schema：完成性由顶层 `classification`、`scenario_count`、`evaluation.scenarios` 与 `metric_summary.coverage_status` 共同判定，未假设不存在的 `completion_status` 字段。

## 验收结果

| 项目 | 结果 |
|---|---:|
| 正式任务 | 16/16 PASS |
| 每任务情景 | 4,657/4,657，ID 集合与顺序一致 |
| 总情景记录 | 74,512 |
| 每任务产品局部块 | 632 |
| 非 `OPTIMAL` 情景 | 0 |
| 成本分解不一致 | 0 |
| 一阶段哈希变化 | 0 |
| numerical fallback 事件 | 17 |
| fallback 最大原始约束违反量 | `7.860861295228005e-09` |
| 冻结可行性容差 | `1e-08` |
| checkpoint 记录运行时间合计 | `23.4252439001575 s` |

Fallback 事件分布为：210202 Robust 1 次；210310 Existing 7 次、Robust 4 次；210611 Existing 4 次；210628 Existing 1 次；其余任务为 0。这里的 fallback 是报告 tie-break 数值偏离时返回已验证经济阶段解，不改变一阶段政策。

## 核心统计复算与科学解释

派生比较表包含 8 个案例、6 个二阶段指标和名义/情景集合算术均值/各指标自身最坏值三种汇总，另附一阶段重配置支出，共 152 行。4,657 个情景没有概率，因此表中的 mean 只能解释为“冻结枚举集合上的等权算术均值”，不能称为期望值。

以 `1e-6` 为实质相同容差：

- 4 个发生实质重配置的案例中，Robust 的名义、均值和最大总缺货量均略高；另外 4 个案例实质相同。因此没有“Robust 系统性减少物理缺货量”的证据。
- 同一 4 个案例的缺货惩罚成本在名义、均值和各自最大值下均下降。这与总缺货方向不同，表明配置改变了缺货在产品间的经济暴露，而非简单减少缺货单位数。
- 4 个实质重配置案例的最坏经济追索成本下降，平均相对变化为 `-0.0735%`；但其名义经济追索成本均上升，平均相对变化为 `+0.1001%`。这支持“名义效率与最坏经济保护之间存在小幅权衡”，不支持“所有情景总成本均改善”。
- 210310、210428、210611、210628 两政策的主要指标在 `1e-6` 内相同；极小差异属于数值量级。
- 运输成本在 4 个实质重配置案例下降，而服务超限量上升。经济追索的变化必须由三个成本分项共同解释，不能把缺货惩罚下降等同于追索成本必然下降。

各指标的最坏情景分别求取；例如最大总缺货情景与最大经济追索情景通常不同，任何一列都未借用另一列的场景身份。

## 一阶段重配置成本

Existing 的 `a+`、`a-` 冻结坐标为零，因此其重配置支出为零。Robust 的 `reconfiguration_spending` 直接读取对应 SCAL_BASE `result.json`：210129、210202、210323、210330 分别为 `248.104699`、`478.823511`、`89.141024`、`139.228403` 成本单位；其余四例在 `1e-6` 内为零。该分项来自 Robust 来源实验，不属于 V2R1 二阶段 `recourse_cost`，不得与二阶段成本重复相加或称为 V2R1 总成本。

## 归档与可复核文件

- 正式结果压缩包：`artifacts/e2_stockout_common_scenario_formal_v2r1_results.zip`，包含 32 个文件（16 个 checkpoint 与 16 个 sidecar），与本地展开的 V2R1 结果逐字节一致。
- 资源预检压缩包：`artifacts/e2_stockout_resource_preflight_v2r1.zip`，包含 checkpoint、sidecar 与 result manifest 共 3 个文件，与本地预检目录逐字节一致。
- 机器验收：`experiments/audits/e2_stockout_v2r1_acceptance.json`。
- 派生比较表：`experiments/analysis/e2_stockout_v2r1_policy_comparison.csv`。
- 完整交付哈希：`experiments/audits/e2_stockout_v2r1_archive_sha256.json`。

压缩包 SHA-256 为 `739b895b3c4aa78ae9cfa6bf2ffc47769502da61b63ee2e6f06471c78ce6ddce`。展开 checkpoint、pytest 临时目录、个人备份、V1/V2 部分结果与无关绘图脚本不纳入提交。

## 限制

V2R1 是固定一期政策的共同情景二阶段评价，不是重新求解包含一期成本的完整优化目标。因而它能够支持物理缺货、服务超限和二阶段经济暴露的比较；不能单凭二阶段追索差异宣称全生命周期总成本下降，也不能证明恢复速度、客户流失或供应中断恢复能力。

## 验证与遗留测试状态

只读验收脚本连续两次生成完全相同的 CSV、验收 JSON 和 SHA 清单；`py_compile` 与 `git diff --check` 通过。为遵守零新增求解边界，未运行会调用 `solve_fixed_policy_block` 的 Gurobi 测试。

运行不触发优化的四个 E2 测试文件得到 `17 passed, 6 failed`。失败不是结果数值不一致，而是测试仍假定“正式运行前”生命周期：两项硬编码 `formal_run_authorized=false`/未授权拒绝；四项通过 runner 的当前 manifest 入口验证历史 V2R1 preflight，但该 preflight 的 authorization 和 checkpoint 正确保留的是运行当时的旧 manifest 快照。机器验收已改为用历史 authorization SHA、checkpoint sidecar、result manifest 和资源审计互相闭合，且不篡改旧哈希。Draft PR 不应把这 6 项描述成全套通过；后续若要恢复绿色测试，应新增明确的 post-run archive 测试口径，而不是改写历史 preflight 或正式授权事实。
