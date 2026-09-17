# Large-scale iteration mechanism

## Scientific role

Pure Benders is used as an iteration-mechanism baseline. It maintains one aggregate recourse representation. PRB retains product-risk-budget states in the master. The paired comparison asks whether the finer risk information reduces repeated master-subproblem interaction.

The design contains three controlled network scales and ten seeds per scale. A Pure-PRB pair enters the paper table and figure only when both solutions are exactly certified and their objectives agree within `1e-4`. The three preserved Pure ERROR observations therefore remain in completeness reporting but not in the certified paired iteration statistics.

## Pure Benders versus PRB

| Scale | Paired n | Pure median | PRB median | Median PRB/Pure | Median reduction | Fewer / equal / more |
|---|---:|---:|---:|---:|---:|---:|
| L10 | 9 | 13 | 6 | 0.455 | 54.5% | 9 / 0 / 0 |
| XL10 | 9 | 12 | 6 | 0.455 | 54.5% | 9 / 0 / 0 |
| XXL10 | 9 | 14 | 6 | 0.429 | 57.1% | 9 / 0 / 0 |
| pooled | 27 | 13 | 6 | 0.444 | 55.6% | 27 / 0 / 0 |

Across the controlled large-scale instances, PRB consistently requires fewer Benders iterations than Pure Benders, indicating that retaining product-level risk-budget information in the master reduces repeated master-subproblem interaction.

在受控的大规模仿真实例中，PRB 相比纯 Benders 整体需要更少的分解迭代轮次，表明在主问题中保留产品—风险预算信息能够减少重复的主从问题交互。

## Aggregate with structured oracle versus PRB

The pooled certified comparison contains 30 pairs. The median PRB/Aggregate iteration ratio is 0.466, with 30 fewer, 0 equal, and 0 more iteration counts.

All non-iteration diagnostics remain available in the complete audit tables and raw results. They are outside this paper mechanism statement.
