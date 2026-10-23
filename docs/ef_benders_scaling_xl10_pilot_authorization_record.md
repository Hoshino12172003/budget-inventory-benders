# EF-BD XL10 pilot authorization record

- Protocol: `EF_BD_XL10_SINGLE_PILOT_V1`
- Condition: `EF_XL10_S20260921`
- Attempt: `attempt-001`
- Authorization: `formal_run_authorized=false`
- Decision: `READY_FOR_AUTHORIZATION` only after all live dry-run gates pass
- Retry: forbidden without a new, separately reviewed protocol and authorization

This record prepares but does not authorize optimization. A later authorization commit may change only the versioned authorization field after repeating identity, environment, resource, process, Git, and output-absence checks.
