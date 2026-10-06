# ADR 0004: A gated cutover with automatic rollback to the untouched source

**Status:** Accepted
**Context:** The cutover is the only moment the shop stops. It must be short, must not switch to a database
that's behind, and must have a way back that doesn't depend on someone improvising at midnight.

## Options considered

| Option | Verdict |
|---|---|
| A checklist run by hand | ❌ Each check is a judgement under pressure; nothing stops a step being skipped |
| Switch first, reconcile afterwards | ❌ Orders taken on Aurora while it's missing data can't simply be thrown away |
| **A script with gates and time limits; any failed gate restarts the app on the source** | ✅ Chosen |

## Decision

[`scripts/cutover.py run`](../../scripts/cutover.py): stop the app → counts equal (10-minute limit) → validation
complete with 0 pending, failed or suspended (15-minute limit) → stop DMS → add the foreign keys (on failure, resume
DMS) → start the app on Aurora (on failure, start it on the source again). Downtime is read from the application's
log: last order on the source to first order on Aurora.

## Consequences

- Measured: 284.8 s, every gate passed, no rollback needed.
- Rollback is cheap because nothing ever writes to the source except the application, and DMS keeps its position.
- The time limits are business decisions, agreed before the night: they decide how long the shop may stay closed
  before the answer becomes "not tonight".
