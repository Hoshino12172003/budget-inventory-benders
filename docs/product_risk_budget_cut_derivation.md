# Product recourse cut derivation

Fix product `j`, an exact shock pattern `S` with `|S|=g`, and inventory vector `x_j`. Let `d_r(S)` be the resulting demand and let

```text
A(S) = (1-service_level_j) sum_r d_r(S).
```

The product recourse primal is

```text
min  sum_i,r c[i,r,j] q[i,r] + sum_r p[r,j] u[r] + s[j] e
s.t. sum_i q[i,r] + u[r] >= d_r(S)                 [pi_r >= 0]
     sum_r q[i,r] <= x[i,j]                        [mu_i <= 0]
     sum_r u[r] - e <= A(S)                        [sigma <= 0]
     q, u, e >= 0.
```

With these constraint orientations, its dual is

```text
max  sum_r d_r(S) pi_r + sum_i x[i,j] mu_i + A(S) sigma
s.t. pi_r + mu_i <= c[i,r,j]                       for every i,r
     pi_r + sigma <= p[r,j]                        for every r
     -sigma <= s[j]
     pi_r >= 0, mu_i <= 0, sigma <= 0.
```

For an optimal dual solution at generation point `xbar_j`, define

```text
alpha = sum_r d_r(S) pi_r + A(S) sigma
beta_i = mu_i.
```

Weak duality gives a global lower support for the fixed pattern:

```text
Q_j(x_j,S) >= alpha + sum_i beta_i x[i,j].
```

The chosen pattern is a maximizer of `Q_j(xbar_j,S)` among all exact-`g` patterns. Since

```text
V[j,g](x_j) = max_{|S|=g} Q_j(x_j,S),
```

the same affine function is globally valid for `V[j,g]`. Strong duality makes it tight at `xbar_j`. The implementation checks all dual-variable signs, all three classes of dual constraints, and primal/dual equality for every generated cut.

This sign convention also explains why inventory coefficients are nonpositive: an increase in available product inventory cannot increase optimal recourse cost.
