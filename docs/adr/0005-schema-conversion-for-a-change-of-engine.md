# ADR 0005: A change of engine starts with schema conversion; measured here, not built

**Status:** Accepted (production path documented; not built in this lab)
**Context:** The board asked whether the order database could move to PostgreSQL instead of Aurora MySQL. DMS
moves data between engines, but a heterogeneous move also needs the schema (and the application's SQL) converted.

## Options considered

| Option | Verdict |
|---|---|
| Let DMS create the PostgreSQL tables and call it done | ❌ Measured: 0 of 3 foreign keys, 1 index per table, no defaults, no auto-increment; the app's INSERT fails |
| **DMS Schema Conversion (or AWS SCT) first, then DMS into the converted schema** | ✅ The production path |
| Build Schema Conversion in this lab | ❌ Its own instance profile, IAM roles, S3 bucket and networking would double the build for a question the inspection already answers |

## Decision

In this lab, one DMS full load into PostgreSQL with `DROP_AND_CREATE`, and an inspection of both sides, to produce
the evidence: what a conversion has to add ([`mysql-to-postgresql.md`](../mysql-to-postgresql.md)). For a real
move: convert the schema with DMS Schema Conversion, review its conversion report, create the converted schema,
load it with DMS into the existing tables, convert the application's MySQL-specific SQL, then validate and
rehearse the cutover as for Aurora.

## Consequences

- The board gets a concrete answer: Aurora MySQL is a data migration; PostgreSQL is a schema and application
  migration that includes a data migration.
- The conversion itself, and its report of what needs hand work, isn't demonstrated here.
