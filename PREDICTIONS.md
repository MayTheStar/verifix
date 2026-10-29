# Predictions for the generalization suite (written BEFORE running v1)

System under test: v1 (frozen), with one policy change: `cache_ttl_s` added to allowed config keys.

| Family | Expected correct outcome | Predicted pass rate (of 3) | Reasoning |
|---|---|---|---|
| bad_config_payments | RECOVERED | 3/3 | Same pattern as bad_config; the investigation gate forces reading config and deploys. |
| cache_stampede | RECOVERED | 1/3 | New pattern; the model may raise max_connections on the database (a trap). |
| external_outage | ESCALATED | 1/3 | No fix exists; the model may keep trying actions instead of escalating. |
| approval_denied | ESCALATED | 2/3 | The prompt says to escalate if approval is not granted. |

Baselines: B1 cannot escalate, so it should score 0 on the two ESCALATED families.

## v2 (futility guard), written BEFORE running
- external_outage: expect 3/3 ESCALATED (guard forces escalation after 4 failed actions).
- cache_stampede: expect unchanged (1/3); the guard does not help diagnosis.
- bad_config_payments, approval_denied: expect unchanged (3/3 each).
- Risk: the guard could block a legitimate fix on a hard case. Dev/heldout regression will check this.
- NOTE: v2 was designed after viewing gen traces, so the gen result is NOT held-out.