# MySQL to PostgreSQL: what DMS carries across, and what it doesn't

The board's second question was "could we move to PostgreSQL instead?" DMS will move the data; the real
question is what it doesn't move. I answered it with measurements: one DMS full load from the same MySQL
source into RDS for PostgreSQL 16, with `TargetTablePrepMode: DROP_AND_CREATE`, so DMS designed the tables
itself. Then I inspected both sides with the same questions
([`sql/inspect-source.sql`](../sql/inspect-source.sql), [`sql/inspect-postgres.sql`](../sql/inspect-postgres.sql)).

The source was quiet by then (the application was trading on Aurora), so this was a clean point-in-time copy.

## The data: all of it, validated

[`26`](screenshots/26-step11-postgres-full-load.png), [`postgres-tables.csv`](results/postgres-tables.csv)

| Table | Rows loaded | Validation |
|---|---|---|
| customers | 5,000 | Validated, 0 failed |
| products | 500 | Validated, 0 failed |
| orders | 201,688 | Validated, 0 failed |
| order_items | 401,688 | Validated, 0 failed |

608,876 rows; the task was stopped with `FULL_LOAD_ONLY_FINISHED` at the 113 s check. On data alone, a success.

## The schema: most of it missing

[`27`](screenshots/27-step11-inspect-source.png), [`28`](screenshots/28-step11-inspect-postgres.png)

| | MySQL source | PostgreSQL (DMS-created) | What it breaks |
|---|---|---|---|
| Indexes: customers | 2 (PK + unique email) | 1 (PK) | duplicate email addresses accepted |
| Indexes: products | 2 (PK + unique SKU) | 1 (PK) | duplicate SKUs accepted |
| Indexes: orders | 3 (PK + customer + status/created) | 1 (PK) | "a customer's orders" and "new orders today" become full scans |
| Indexes: order_items | 3 (PK + order + product) | 1 (PK) | loading an order's lines becomes a full scan |
| Foreign keys | 3 | **0** | orphaned order lines and orders for missing customers accepted |
| `order_id` | `int unsigned`, `auto_increment` | `bigint`, no default | **the application can't insert an order** |
| `status` | `enum('NEW','PAID','SHIPPED','CANCELLED')`, default `NEW` | `character varying(9)`, no default | any text up to 9 characters accepted as a status |
| `total_zar` | `decimal(12,2)`, default `0.00` | `numeric` (scale 2 kept), no default | an insert that leaves out the total no longer gets 0.00 |
| `created_at` | `datetime(3)`, default `CURRENT_TIMESTAMP(3)` | `timestamp without time zone`, no default | nothing fills the creation time any more |
| `updated_at` | `datetime(3)`, default + `ON UPDATE CURRENT_TIMESTAMP(3)` | `timestamp without time zone`, no default | updates no longer record when they happened |

Two choices DMS made are sensible: `int unsigned` became `bigint` (an unsigned 32-bit value can exceed
PostgreSQL's signed `integer`), and the ENUM became a string exactly as long as its longest value, "CANCELLED"
(9 characters). My inspection query shows type names only. The failing row below shows `0.00` for an inserted `0`, so `numeric`
kept a scale of 2; the precision of `numeric` and `timestamp` is for a schema review to confirm.

## The proof: the application's own insert

The last statement in `inspect-postgres.sql` is the application's normal insert, which on MySQL gets its
`order_id` from `AUTO_INCREMENT`:

```sql
INSERT INTO ubuntu_retail.orders (customer_id, status, total_zar) VALUES (1, 'NEW', 0);
```

PostgreSQL's answer:

```
ERROR:  null value in column "order_id" of relation "orders" violates not-null constraint
DETAIL:  Failing row contains (null, 1, NEW, 0.00, null, null).
```

The failing row says the rest: no id, and `created_at` / `updated_at` null, because nothing fills them any more.
(Whether DMS kept those two columns `NOT NULL` my inspection didn't check; PostgreSQL reported the first violation.)

## What a real move to PostgreSQL needs

The table above is the work list. In production I'd convert the schema before moving any data:

1. **Convert the schema with DMS Schema Conversion** (or the AWS Schema Conversion Tool): identity columns or
   sequences for the auto-increment keys, CHECK constraints or a PostgreSQL ENUM type for `status`, defaults,
   the unique and secondary indexes, the foreign keys, and a trigger to replace `ON UPDATE`. The conversion
   report lists what it can't convert automatically, and that becomes the hand-written part.
2. **Create the converted schema on the target**, then run DMS with `DO_NOTHING` or `TRUNCATE_BEFORE_LOAD`, so
   DMS fills tables someone designed, as it did on Aurora.
3. **Convert the application's SQL**: MySQL-specific syntax (here `LAST_INSERT_ID()`, `RAND()` and session variables)
   doesn't run on PostgreSQL unchanged.
4. **Validate and rehearse the cutover** exactly as for Aurora.

I didn't build step 1 here. Its network, IAM and S3 requirements would have doubled the build for a question
this inspection already answers, so it's documented as the production path
([ADR 0005](adr/0005-schema-conversion-for-a-change-of-engine.md)).

**The lesson for Ubuntu Retail:** moving to Aurora MySQL is a data migration. Moving to PostgreSQL is a schema and
application migration that happens to include a data migration.
