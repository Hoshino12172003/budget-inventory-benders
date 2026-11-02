# §5.3 已有五类敏感性实验的证据清单

## 审查结论

§5.3 直接复用仓库已有 E3–E7 五类实验，不新增敏感性维度，也不重新设计或运行实验。这五类实验均使用 `RENAULT_EMPIRICAL_8CASE_V1` 的八个案例，并在每个参数单元重新优化一期配置（身份安全的重用单元除外，重用的是同一参数条件下已经求得的一期解）。它们不是 E2 V2R1 那种“固定两种一期政策、在同一 4,657 情景集上再评价”的设计。

当前 checkout 不包含 E3–E7 授权文件所指向的展开原始 result roots，也不包含最终审计所述的五个 frozen ZIP。仓库内存在正式授权、最终审计、协议、解释文档和派生 CSV；最终审计记录其当时曾逐文件核对原始结果与 frozen ZIP。故本轮可以复用已提交的正式派生证据和审计结论，但不能在当前 checkout 独立重算全部原始 JSON 哈希。该可移植性缺口必须在论文复现包发布前补齐，不能用现有表格冒充当前可访问的原始结果。

## 逐实验口径

| 项目 | E3 财务预算 | E4 不确定性预算 | E5 重配置摩擦 | E6 预算×风险 | E7 风险×摩擦 |
|---|---|---|---|---|---|
| 实验 ID | `E3_FINANCIAL_BUDGET_SENSITIVITY_V1` | `E4_GAMMA_SENSITIVITY_V1` | `E5_RECONFIGURATION_FRICTION_SENSITIVITY_V1` | `E6_BUDGET_RISK_INTERACTION_V1` | `E7_RISK_FRICTION_INTERACTION_V1` |
| 改变参数 | `beta={0.8,0.9,1.0,1.1,1.2}` | `Gamma={0,1,2,3,4}` | `lambda_R={0,0.0025,0.01,0.05,0.2}` | `beta={0.8,1.0,1.2}` × `Gamma={0,2,4}` | `Gamma={0,2,4}` × `lambda_R={0.0025,0.05,0.2}` |
| 固定参数 | `Gamma=2, lambda_R=0.05` | `beta=1, lambda_R=0.05` | `beta=1, Gamma=2` | `lambda_R=0.05` | `beta=1` |
| 案例 | 8 Renault-derived | 同左 | 同左 | 同左 | 同左 |
| 一期处理 | 各 beta 重新优化；B100 8 例复用 | 各 Gamma 重新优化；G2 8 例复用 | 各 lambda 重新优化；L0500 8 例复用 | 每个 3×3 单元优化或身份验证重用 | 每个 3×3 单元优化或身份验证重用 |
| 规划/评价不确定集 | 同一单元均为 `Gamma=2` | 随 Gamma 同时改变规划问题及最坏评价集合 | 同一单元均为 `Gamma=2` | Gamma 同时改变规划问题及最坏评价集合 | Gamma 同时改变规划问题及最坏评价集合 |
| 比较方法 | 案例内预算网格、B100 归一化 | 案例内 Gamma 网格、G0 归一化 | 案例内摩擦网格、L0500 归一化 | 3×3 描述性交互对比 | 3×3 描述性交互对比 |
| 完成数 | 40/40 | 40/40 | 40/40 | 72/72 | 72/72 |
| 最终审计 | PASS | PASS | PASS | PASS，带运行计时口径限制 | PASS |
| 正式证据 | 是（当前为审计+派生表；原始 root/ZIP 缺席） | 同左 | 同左 | 同左 | 同左 |

## 原始与派生证据定位

### E3 — Financial budget sensitivity

- 协议：`docs/e3_financial_budget_sensitivity_protocol.md`。
- 授权：`experiments/configs/formal/e3_budget_sensitivity_authorization.json`。
- 声明原始 root：`experiments/results/e3_budget_sensitivity_v1`（当前缺失）。
- 最终审计：`artifacts/e3_final_result_audit.json`，记录 40/40、全部最优且精确认证、120 个主文件与 frozen ZIP 字节一致；该 ZIP 当前缺失，审计记录哈希为 `4c17959f50f4dcb3690058736cec73cd44a6f7ac28eea103b0ed391d52d20e09`。
- 可用表：`e3_table_budget_sensitivity_case_level.csv`、`e3_table_budget_sensitivity_aggregate.csv`、`e3_table_budget_thresholds.csv`。
- 可支持：预算收紧与重配置强度、目标/追索变化、预算利用率和经验平台区间的描述。
- 不可支持：Renault 实际财务预算、连续阈值或因果结论；不能将 E3 的最坏场景指标直接与 E2 的共同情景固定政策差异相减。

### E4 — Gamma sensitivity

- 协议：`docs/e4_gamma_sensitivity_protocol.md`；授权：`experiments/configs/formal/e4_gamma_sensitivity_authorization.json`。
- 声明原始 root：`experiments/results/e4_gamma_sensitivity_v1`（当前缺失）。
- 最终审计：`artifacts/e4_final_result_audit.json`，40/40，`E4_FINAL_AUDIT_PASS`。
- 可用表：`e4_table_gamma_sensitivity_case_level.csv`、`e4_table_gamma_sensitivity_aggregate.csv`、`e4_table_reconfiguration_thresholds.csv`。
- 可支持：在各 Gamma 下重新优化时，经济暴露与重配置反应如何随风险预算变化；案例触发异质性。
- 不可支持：相同压力测试下仅由配置变化导致的纯效应。Gamma 同时定义规划不确定集和对应最坏评价集合，不同 Gamma 的 worst-case cost 不在同一冻结场景集上。

### E5 — Reconfiguration friction sensitivity

- 协议：`docs/e5_reconfiguration_friction_protocol.md`；授权：`experiments/configs/formal/e5_reconfiguration_friction_authorization.json`。
- 声明原始 root：`experiments/results/e5_reconfiguration_friction_v1`（当前缺失）。
- 最终审计：`artifacts/e5_final_result_audit.json`，40/40，`E5_FINAL_AUDIT_PASS`。
- 可用表：`e5_table_friction_sensitivity_case_level.csv`、`e5_table_friction_sensitivity_aggregate.csv`、`e5_table_friction_response_by_case.csv`。
- 可支持：摩擦系数通过目标中的移动成本及共享预算约束改变调整幅度、组成与经济追索；在测试网格上影响较小且非单调。
- 不可支持：单调定理、连续阈值，或把 `lambda_R` 解释为观测到的 Renault 参数。

### E6 — Budget × risk interaction

- 协议：`docs/e6_budget_risk_interaction_protocol.md`；授权：`experiments/configs/formal/e6_budget_risk_interaction_authorization.json`。
- 声明原始 root：`experiments/results/e6_budget_risk_interaction_v1`（当前缺失）。
- 最终审计：`artifacts/e6_final_result_audit.json`，72/72，`PASS_WITH_RUNTIME_ACCOUNTING_LIMITATION`；40 个复用、32 个新正式单元。
- 可用表：`e6_table_budget_risk_interaction_case_level.csv`、`e6_table_budget_risk_interaction_aggregate.csv`、`e6_table_interaction_contrasts.csv`、`e6_table_depot_response.csv`。
- 可支持：预算紧张下重配置可能提前饱和，决策交互强于经济交互，以及严重财务稀缺时的规划期仓库收缩。
- 不可支持：因果 difference-in-differences；历史总 wall-clock 无法从只记录核心 PRB 时间的旧字段精确恢复。

### E7 — Risk × friction interaction

- 协议：`docs/e7_risk_friction_interaction_protocol.md`；授权：`experiments/configs/formal/e7_risk_friction_interaction_authorization.json`。
- 声明原始 root：`experiments/results/e7_risk_friction_interaction_v1`（当前缺失）。
- 最终审计：`artifacts/e7_final_result_audit.json`，72/72，`E7_FINAL_AUDIT_PASS`；40 个复用、32 个新正式单元。
- 可用表：`e7_table_risk_friction_case_level.csv`、`e7_table_risk_friction_aggregate.csv`、`e7_table_interaction_contrasts.csv`、`e7_table_adjustment_composition.csv`。
- 可支持：摩擦主要抑制高风险下的调整强度和分散度，而测试网格中的首次实质调整 Gamma 基本不变。
- 不可支持：恢复速度、服务指标的普遍改善或摩擦触发阈值的连续定理。

## 与 §5.2 的可比性边界

五类实验与 E2 使用相同八案例和模型家族，因此可作为经济保护边界条件的补充机制证据；但没有一类等同于 E2 V2R1 的固定 Existing/Robust 共同 4,657 情景评价。§5.2 的因变量比较是既定政策在同一需求清单上的追索表现，§5.3 的比较是参数变化后重新优化所得的稳健方案及其各自不确定集表现。两者可形成“基准效应—边界条件”的叙事，不能进行跨实验单元的直接差值归因。
