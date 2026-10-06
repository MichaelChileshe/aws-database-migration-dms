# ADR 0001: Full load + CDC with AWS DMS, for minutes of downtime instead of a weekend

**Status:** Accepted
**Context:** Ubuntu Retail's last database move was an offline export and import over a weekend. The board's rule
for the order database: minutes of downtime, and proof that nothing was lost. Orders arrive all day.

## Options considered

| Option | Verdict |
|---|---|
| `mysqldump` export, import into Aurora, switch | ❌ The shop is closed for the whole dump, transfer and import; time grows with the data |
| Native MySQL replication from the source to Aurora (binlog replication) | ⚠️ Works for MySQL to Aurora MySQL, but gives no row-by-row validation and doesn't help with the PostgreSQL question |
| **DMS task: full load + CDC, validation on** | ✅ Chosen |

## Decision

One DMS task, `retail-orders-to-aurora` (migration type `full-load-and-cdc`), from the on-premises MySQL to Aurora MySQL: the full copy runs while the shop
trades, then CDC applies every later change from the binary log until the cutover. Validation is on for the
whole run, with validation-only tasks for point-in-time checks.

## Consequences

- The shop only stops for the cutover: measured at 284.8 s. Aurora was already level on the
  first count check; most of the time went on proving it ([`cutover-runbook.md`](../cutover-runbook.md)).
- The source must have the binary log on, in ROW format with FULL row images and enough retention. Trap 1 showed
  the failure when it isn't ([`trap-drills.md`](../trap-drills.md)); on a real server, enabling it is a restart
  planned before the migration starts.
- A replication instance runs (and bills) from the full load until the cutover is signed off.
