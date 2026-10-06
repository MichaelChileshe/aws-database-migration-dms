# The cutover runbook

The cutover is the only part of the migration where the shop stops taking orders. I wrote it as a sequence of
gates in [`scripts/cutover.py`](../scripts/cutover.py): each step happens only when the one before it is
proven, and any gate that isn't met in time puts the shop back on the old database.

Before running it: DMS in CDC with nothing failed, the app trading on the source, and the application user
created on Aurora (`retail-db users-aurora`), because DMS copies data, not MySQL accounts.

## The gates

| # | Step | Proven by | If it fails |
|---|---|---|---|
| 1 | Stop the application: **downtime starts** | `orders-app stop` | (nothing to roll back yet) |
| 2 | Gate: Aurora's row counts equal the source's | four table counts and the newest `order_id`, compared every 5 s (10-minute limit) | restart the app on the source; DMS keeps running |
| 3 | Gate: DMS validation complete | every table `Validated`, 0 pending, 0 failed, 0 suspended (15-minute limit) | same rollback |
| 4 | Stop the DMS task | `wait replication-task-stopped` | |
| 5 | Add the three foreign keys on Aurora | `ALTER TABLE ... ADD CONSTRAINT` checks every existing row | resume DMS, restart the app on the source |
| 6 | Start the application against Aurora: **downtime ends** | the app's log shows `OK aurora` | restart the app on the source |

The rollback is cheap because the source is never changed: rolling back means pointing the application where it
already was.

## The run

[`23`](screenshots/23-step10-cutover-gates.png), [`24`](screenshots/24-step10-cutover-downtime.png),
[`cutover-results.csv`](results/cutover-results.csv):

```
09:59:41 UTC  1. stopping the application (orders stop being taken)
    2026-10-06T09:59:42.417Z OK source order=201688
09:59:46 UTC  2. gate: Aurora row counts equal the source
    orders 201,688 / 201,688   order_items 401,688 / 401,688   (missing 0 everywhere)
09:59:58 UTC  3. gate: DMS validation complete
    validation pending 475 ... 286 ... 186 ... 86 ... customers, order_items, orders, products: Validated
10:03:16 UTC  4. stopping the DMS task
10:03:51 UTC  5. adding the foreign keys on Aurora
    fk_items_order, fk_items_product, fk_orders_customer
10:04:25 UTC  6. starting the application against Aurora

last order on the source  09:59:42.417 UTC
first order on Aurora     10:04:27.236 UTC
DOWNTIME (no orders taken): 284.8 s
```

| Phase | Seconds | Share |
|---|---|---|
| Count gate (equal on the first check) | 11.9 | 4% |
| **Validation gate** | **197.4** | **69%** |
| Stop the DMS task (confirmed by the CLI waiter, which checks every 15 s) | 35.7 | 13% |
| Add the foreign keys | 33.3 | 12% |
| App stop and start, before the first gate and after the last (the remainder) | 6.5 | 2% |
| **Total** | **284.8** | |

30 seconds later the app was writing to Aurora with 0 failures, Aurora was at 201,871 orders, and DMS's final
statistics showed every table `Validated`, 0 pending, 0 failed
([`25`](screenshots/25-step10-app-on-aurora-final-stats.png)). The new orders continued from 201,689 upwards
because the Aurora tables were pre-created with `AUTO_INCREMENT`, so the counter carried on after the migrated
ids.

## Where the time went, and what I'd change

Aurora was already level with the source on the first count check; most of those 11.9 s were the check itself
(two SSM round trips). More than two thirds of the downtime was spent proving it: DMS validates
recent changes a little behind the changes themselves, and the gate waited for the last 475 records.

Options for a shorter window, each a trade-off for the business to choose, not for me to choose quietly:

- **Gate on counts, validate straight after.** About 3 minutes shorter here (197.4 s). The risk: switching on a change that
  validation would have flagged, found minutes later instead of before. The source still holds everything, so it's
  recoverable, but orders taken on Aurora in between would need reconciling.
- **Watch validation lag before stopping the app.** Start the cutover when pending validation is near zero, so
  the gate has less to catch up on.
- **Add the foreign keys after the switch.** Saves about 33 s, but the integrity check would happen with the
  shop already trading on Aurora.
- **Test more validation threads.** The task used 5 (`ValidationSettings.ThreadCount`). Whether more threads
  shorten this on a dms.t3.medium is a measurement for the next rehearsal, not an assumption.

Stopping the DMS task was confirmed 35.7 s after the request. The CLI waiter that confirms it checks every 15 s, so
the stop itself took somewhere between about 21 and 36 s. Either way it's a cost worth knowing before promising a
number to the board, and the foreign-key step's 33.3 s likewise includes an SSM round trip.

## Running it for real

- Rehearse on a copy first. In this lab the trap drills ran on the live migration task; in production I'd run
  them against a copy before the real night.
- Agree the gates and their time limits with the business before the night, including who decides to roll back.
- Keep the source untouched, and keep DMS's task and the source running until Aurora has traded for long enough to
  trust it.
- Read the downtime from the application's own log, not from the runbook's clock: it's the number customers
  experienced.
