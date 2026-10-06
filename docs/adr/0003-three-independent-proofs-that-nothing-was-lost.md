# ADR 0003: Three independent proofs that nothing was lost

**Status:** Accepted
**Context:** "Prove nothing was lost" has to survive an auditor. A full load at 100% isn't proof: trap 2 left 142
orders missing without a single error anywhere.

## Options considered

| Option | Verdict |
|---|---|
| Trust the task status and table statistics | ❌ Status doesn't mean caught up; the CDC counters even restart on resume |
| Row counts only | ⚠️ Catches missing rows, not changed values (it would miss the 108 `RECORD_DIFF` orders) |
| **DMS validation + validation-only tasks + count gates + foreign keys** | ✅ Chosen |

## Decision

- **Validation on the main task** (`ValidationSettings.EnableValidation`, 5 threads): DMS compares every row it
  migrates, and keeps comparing changes during CDC.
- **Validation-only tasks** (`ValidationOnly: true`, `DO_NOTHING`) for a point-in-time comparison of the whole
  database, with every difference written to `awsdms_control.awsdms_validation_failures_v1` on the target.
- **Count gates** in the cutover: all four tables and the newest `order_id`.
- **Foreign keys** added at cutover, which checks every reference.

## Consequences

- Trap 2 was caught two ways: counts (142 missing) and validation-only (392 failed: 284 `MISSING_TARGET`,
  108 `RECORD_DIFF`); after the fix both showed zero. The foreign keys were the third check, at the cutover.
- Validation needs a primary key or unique index on every table (all four have one).
- Validation trails the changes, which made the validation gate the longest part of the cutover (197.4 s).
