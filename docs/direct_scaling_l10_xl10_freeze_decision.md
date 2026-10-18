# Direct scaling L10 and XL10 freeze decision

## Decision

L10 and XL10 are formally frozen. No further XL10 Direct retries are authorized. XXL10 has not been executed and is outside the completed-scale statistics.

## Frozen counts

- L10: 10/10 exact-certified.
- XL10: 9/10 exact-certified; 1/10 resource failure.
- Combined completed-scale scope: 19 certified, 1 resource failure, 0 time failures, 0 numerical-certification failures, 0 unexecuted.
- Valid four-method pairs: 19. `DIRECT_XL10_S20260924` is excluded from paired timing but retained in the ten-condition XL10 completion denominator.

## Terminal XL10 failure

`DIRECT_XL10_S20260924` attempt-001 and attempt-002 both stopped at `RESOURCE_PROCESS_CAP`. Attempt-002's last solver-progress record implies a 0.382551% gap; this is interrupted, unverified progress and is not a final exact or certified gap.

## Comparability boundary

Direct protocols and their resource limits, Method, and Threads settings are preserved in the manifest. The historical Scaling V2 solver version remains `NOT_VERIFIABLE`; exact software-environment identity is not claimed.

No optimizer or instance generator is invoked by the freeze script.
