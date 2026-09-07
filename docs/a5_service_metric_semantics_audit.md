# A5 service metric semantics audit

This audit does not change the mathematical model or any frozen parameter.

The acceptance runner called the same exact post-evaluator for A3, A4, and A5,
but passed each run's optimization `Gamma`. A3 and A4 therefore used the single
nominal `Gamma=0` realization. A5 used the complete `Gamma=2` binary-budget
uncertainty set. Its 96 region-product uncertainty items produce 4,657 extreme
scenarios. The original A3/A4 and A5 service columns consequently were not a
common-scenario comparison.

The optimization objective is first-stage expenditure plus maximum recourse
cost over the uncertainty set. Recourse cost contains transportation cost,
region-product shortage penalties, and a soft product-level service-violation
penalty. The service constraint permits excess shortage through nonnegative
violation variable `e`; it is not a hard minimum regional fill-rate constraint.

`FR_min` is post-evaluation only. The evaluator first fixes inventory and solves
each product-scenario recourse block at minimum economic cost. A deterministic
secondary reporting solve chooses shortage flows without changing block cost
beyond the frozen tolerance. It then reports the minimum product-aggregated
regional fill rate across evaluated scenario-region pairs. The scenario that
minimizes this diagnostic need not be the scenario that maximizes economic
recourse cost.

Service penalty and `FR_min` are not strictly monotone equivalents. The former
is a product-level soft-violation cost inside an objective that also contains
transportation and heterogeneous shortage costs; the latter is an unweighted
regional diagnostic. Robust-objective improvement therefore does not, by
itself, imply improvement of minimum regional fill rate.
