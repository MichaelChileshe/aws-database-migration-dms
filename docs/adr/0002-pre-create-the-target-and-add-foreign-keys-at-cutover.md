# ADR 0002: Pre-create the Aurora tables, without foreign keys; add the keys at cutover

**Status:** Accepted
**Context:** Left to create tables itself, DMS creates tables and primary keys (in some cases unique indexes). The source has unique and
secondary indexes, ENUMs, defaults, AUTO_INCREMENT, an `ON UPDATE` timestamp and three foreign keys. DMS also
loads tables in parallel, so a child row can arrive before its parent.

## Options considered

| Option | Verdict |
|---|---|
| Let DMS create the tables (`DROP_AND_CREATE`) | ❌ Loses the secondary indexes, foreign keys, defaults and AUTO_INCREMENT; the PostgreSQL run measured exactly that |
| Pre-create the full schema, foreign keys included | ❌ The full load runs tables in parallel (and batch-optimised apply can reorder changes), so a child row can arrive before its parent and the key rejects it |
| **Pre-create everything except the foreign keys (`TRUNCATE_BEFORE_LOAD`); add the keys at cutover** | ✅ Chosen |

## Decision

[`sql/target-schema.sql`](../../sql/target-schema.sql) creates the four tables on Aurora exactly as on the source,
minus the foreign keys. The task uses `TRUNCATE_BEFORE_LOAD`, so a restart (like `reload-target` after trap 1)
starts from empty tables without dropping them. [`sql/add-foreign-keys.sql`](../../sql/add-foreign-keys.sql) runs
in the cutover after the DMS task stops.

## Consequences

- Indexes, defaults, ENUMs and AUTO_INCREMENT were in place on day one: after the cutover new orders continued from
  the migrated ids with no change to the application.
- Adding the keys is also an integrity check: it scans every existing row. It took 33.3 s inside the downtime, including an SSM round trip.
- Until cutover, Aurora doesn't enforce references, which is fine because nothing but DMS writes to it.
