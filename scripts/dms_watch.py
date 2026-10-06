#!/usr/bin/env python3
"""Watch a DMS task until it reaches a goal, printing progress every 15 s.

  python3 scripts/dms_watch.py <task-arn> [--until stopped|cdc|validated]

  stopped    wait until the task stops or fails (full-load tasks, failing tasks)
  cdc        wait until the full load is done and the task is applying ongoing changes
  validated  like cdc, and every table's validation is complete with nothing pending

Prints status, full-load %, tables loaded/errored, and validation totals; on failure prints DMS's own message.
"""
import argparse, sys, time
from kit_aws import aws


def task(arn):
    return aws("dms", "describe-replication-tasks", "--filters", f"Name=replication-task-arn,Values={arn}")["ReplicationTasks"][0]


def tables(arn):
    return aws("dms", "describe-table-statistics", "--replication-task-arn", arn).get("TableStatistics", [])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("arn")
    p.add_argument("--until", default="stopped", choices=["stopped", "cdc", "validated"])
    a = p.parse_args()
    t0 = time.time()
    while time.time() - t0 < 3600:
        t = task(a.arn)
        st, s = t["Status"], t.get("ReplicationTaskStats", {})
        ts = tables(a.arn) if st in ("running", "stopped", "failed") else []
        pend = sum(x.get("ValidationPendingRecords", 0) for x in ts)
        fail = sum(x.get("ValidationFailedRecords", 0) for x in ts)
        vstates = sorted({x.get("ValidationState", "-") for x in ts})
        print(f"  +{time.time() - t0:5.0f} s  {st:<9} load {s.get('FullLoadProgressPercent', 0):>3}%  "
              f"tables loaded {s.get('TablesLoaded', 0)} errored {s.get('TablesErrored', 0)}  "
              f"validation pending {pend} failed {fail}  {'/'.join(vstates)}", flush=True)
        if st in ("stopped", "failed"):
            print(f"\nTASK {st.upper()}: {t.get('StopReason', '')}")
            if t.get("LastFailureMessage"):
                print(f"LastFailureMessage: {t['LastFailureMessage']}")
            return
        loaded = ts and all(x.get("TableState") == "Table completed" for x in ts) and s.get("FullLoadProgressPercent", 0) == 100
        if a.until == "cdc" and st == "running" and loaded:
            print("\nFULL LOAD COMPLETE: all tables loaded; the task is now applying ongoing changes (CDC).")
            return
        if a.until == "validated" and st == "running" and loaded and pend == 0 and fail == 0 \
                and all(x.get("ValidationState") == "Validated" for x in ts):
            print("\nVALIDATED: every table Validated, nothing pending, nothing failed.")
            return
        time.sleep(15)
    sys.exit("still not there after an hour: investigate before continuing")


if __name__ == "__main__":
    main()
