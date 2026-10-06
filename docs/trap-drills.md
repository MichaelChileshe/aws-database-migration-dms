# The two trap drills

Before the real cutover I ran the two mistakes I'd most expect on a real database migration, on purpose,
and measured what each one costs. Both are easy to make. Neither shows up until it's too late.

---

## Trap 1 · CDC against a source with the binary log off

**The situation.** MySQL 8.0 turns binary logging on by default, but older servers (5.7 and earlier) often run
without it, and some administrators switch it off when nothing replicates from the server, to save disk. I
switched it off on purpose. DMS's change data capture reads the binary log, so without it there's nothing to read.

**What I did.** MySQL 8.0.46 started with `--skip-log-bin` (`log_bin` 0,
[`06`](screenshots/06-step3-server-and-mysql-binlog-off.png)). I created the three endpoints and tested
them from the replication instance. **All three passed** ([`12`](screenshots/12-step6-connection-tests.png)),
including the source. Then I created the main task, `retail-orders-to-aurora` (migration type `full-load-and-cdc`, validation on), and
started it.

**What happened** ([`13`](screenshots/13-step7-trap1-task-failed.png)):

```
  +  118 s  failed    load   0%  tables loaded 0 errored 0  ...
TASK FAILED: Last Error  Failed in resolving configuration. Stop Reason FATAL_ERROR Error Level FATAL
```

The task's own error says what failed, not why. The why was in its CloudWatch log, `dms-tasks-retail-dms`
([`14`](screenshots/14-step7-trap1-task-log.png), [`15`](screenshots/15-step7-trap1-task-log-cont.png)):

```
[SOURCE_CAPTURE  ]E:  Error Code [10001] : Binary Logging must be enabled for MySQL server [1020418]
[SOURCE_CAPTURE  ]E:  Errors in MySQL server validation. ...
[TASK_MANAGER    ]E:  Failed while preparing stream component 'st_0_...'. [1020418]
[TASK_MANAGER    ]E:  Task 'T2BWJ4ZI25E2XFWQK3AKTA3NLU' encountered a fatal error
```

Nothing had been copied: the task checks the source's CDC prerequisites before the full load starts. That's
the best place for it to fail.

**The fix** ([`16`](screenshots/16-step8-binlog-on-and-app-running.png)): restart MySQL with the settings DMS
documents for a MySQL CDC source.

| Setting | Value | Why |
|---|---|---|
| `log-bin` | on | CDC reads the binary log |
| `binlog_format` | `ROW` | DMS needs the changed rows, not the SQL statements |
| `binlog_row_image` | `FULL` | every column of every changed row, so updates can be applied and validated |
| `binlog_expire_logs_seconds` | `86400` | DMS needs the log to still exist if it falls behind or is paused |
| `server-id` | 1 | required once binary logging is on |

Result: `log_bin` 1, ROW, FULL, 86,400. The data was still there, because MySQL keeps it on the server's disk
between restarts. Restarting the task with `reload-target` then loaded everything and moved into CDC
([`17`](screenshots/17-step8-full-load-and-cdc.png)).

**In real life.** On a real server this restart is a maintenance window of its own, before the migration starts,
and the binary log needs disk sized for its retention. For an RDS for MySQL source the equivalent is automated
backups on plus a binlog retention setting; for an Aurora MySQL source it's `binlog_format` in the cluster
parameter group and a reboot.

---

## Trap 2 · Cutting over before DMS has caught up

**The situation.** "The full load finished, the task says running, let's switch." The orders taken in the last
moments on the old database are still on their way, and if DMS is stopped now they never arrive.

**What I did** ([`18`](screenshots/18-step9-trap2-premature-cutover.png)): with the shop trading on the
source, `scripts/cutover.py premature` stopped the DMS task, let the app keep writing, then stopped the app and
compared both databases.

```
09:39:16 UTC  stopping the DMS task while the app is still writing to the source ...
09:39:36 UTC  task stopped; the app keeps taking orders for 15 s ...
orders-app stopped
2026-10-06T09:40:05.479Z OK source order=201001

                  source      aurora   missing
    customers      5,000       5,000         0
    products         500         500         0
    orders       201,002     200,860       142
    order_items  401,002     400,860       142
    max order_id 201,002     200,860       142
```

**142 orders and 142 order lines** existed only on the old database. Pointed at Aurora at that moment, the shop
would have lost every one of them, with no error anywhere.

**Proving it the auditor's way.** A validation-only task copies nothing; it compares every row on both sides
and writes each difference to `awsdms_control.awsdms_validation_failures_v1` on the target
([`19`](screenshots/19-step9-trap2-validation-only-task.png), [`20`](screenshots/20-step9-trap2-validation-failures.png)):

| Table | Failure type | Records | Meaning |
|---|---|---|---|
| order_items | `MISSING_TARGET` | 142 | the order lines that never arrived |
| orders | `MISSING_TARGET` | 142 | the orders that never arrived (newest: 201000, 201001, 201002) |
| orders | `RECORD_DIFF` | 108 | older orders the app marked SHIPPED after DMS stopped: the row exists on Aurora, with the old status |

392 failed records in total (250 on orders, 142 on order_items). The 108 differences are consistent with the
application's behaviour (the failures table's details column was empty, so this is my reading, not DMS's): each loop marks a random older order SHIPPED, a quarter of the seeded orders were SHIPPED already,
and MySQL doesn't change a row when the new value equals the old, so roughly three in four of 142 updates
change something.

**The fix** ([`21`](screenshots/21-step9-resume-and-counts-match.png),
[`22`](screenshots/22-step9-revalidated-zero-failed.png)): `resume-processing` restarted CDC from the position
DMS had saved in the binary log, and the missing changes arrived. A minute later both sides showed 5,000 /
500 / 201,002 / 401,002. A fresh validation-only task (a new task, so each result stands on its own) found
every table `Validated`, 0 failed.

**In real life.** This is the reason the real cutover ([`cutover-runbook.md`](cutover-runbook.md)) stops the
application first and waits for DMS: counts equal, validation complete, only then stop DMS. And it's why the
source stays untouched until the new database has taken orders: the drill was recoverable only because DMS
kept its position and the old database was still the truth.
