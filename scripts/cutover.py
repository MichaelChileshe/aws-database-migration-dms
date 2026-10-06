#!/usr/bin/env python3
"""The cutover, run as a sequence of gates, with the downtime measured from the application's own log.

  python3 scripts/cutover.py premature    TRAP DRILL: stop the DMS task while the app is still writing, then stop
                                          the app, and count what never reached Aurora
  python3 scripts/cutover.py run          the real cutover:
                                            1. stop the application (downtime starts)
                                            2. gate: row counts on Aurora equal the source
                                            3. gate: DMS validation says every table is Validated, 0 pending, 0 failed
                                            4. stop the DMS task
                                            5. add the foreign keys on Aurora (checks every reference)
                                            6. start the application against Aurora (downtime ends)
                                          If a gate isn't met in time, it restarts the app on the source and stops:
                                          that is the rollback.

Needs: SRC_ID, TASK_ARN (and the app running against the source). Results go to build/.
"""
import csv, json, os, subprocess, sys, time
from datetime import datetime, timezone
from kit_aws import aws, env, ROOT

TABLES = ["customers", "products", "orders", "order_items", "max order_id"]


def ssm(cmd, timeout=300):
    """Run one shell command on the on-prem host; return its output (raises on failure)."""
    iid = env("SRC_ID")
    cid = aws("ssm", "send-command", "--instance-ids", iid, "--document-name", "AWS-RunShellScript",
              "--parameters", json.dumps({"commands": [cmd]}))["Command"]["CommandId"]
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(2)
        r = subprocess.run(["aws", "ssm", "get-command-invocation", "--command-id", cid, "--instance-id", iid,
                            "--output", "json"], capture_output=True, text=True)
        if r.returncode != 0:
            continue
        d = json.loads(r.stdout)
        if d["Status"] in ("Pending", "InProgress", "Delayed"):
            continue
        if d["Status"] != "Success":
            raise RuntimeError(f"{cmd!r} -> {d['Status']}\n{d.get('StandardOutputContent', '')}{d.get('StandardErrorContent', '')}")
        return d.get("StandardOutputContent", "")
    raise RuntimeError(f"{cmd!r} timed out")


def counts(side):
    return [int(x) for x in ssm(f"retail-db counts {side}").split()]


def show_counts(src, tgt):
    print(f"    {'':<14}{'source':>12}{'aurora':>12}{'missing':>10}")
    for name, s, t in zip(TABLES, src, tgt):
        print(f"    {name:<14}{s:>12,}{t:>12,}{s - t:>10,}")


def table_stats():
    return aws("dms", "describe-table-statistics", "--replication-task-arn", env("TASK_ARN")).get("TableStatistics", [])


def stop_task():
    arn = env("TASK_ARN")
    aws("dms", "stop-replication-task", "--replication-task-arn", arn)
    subprocess.run(["aws", "dms", "wait", "replication-task-stopped", "--filters",
                    f"Name=replication-task-arn,Values={arn}"], check=True)


def app_log_times(n=400):
    """(last OK on source, first OK on aurora) from the application's log."""
    last_src, first_aur = None, None
    for line in ssm(f"orders-app log {n}").splitlines():
        parts = line.split()
        if len(parts) < 3 or parts[1] != "OK":
            continue
        ts = datetime.strptime(parts[0], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
        if parts[2] == "source":
            last_src = ts
        elif parts[2] == "aurora" and first_aur is None:
            first_aur = ts
    return last_src, first_aur


def now():
    return datetime.now(timezone.utc)


def premature():
    print("TRAP DRILL: cutting over before DMS has caught up\n")
    print(f"{now():%H:%M:%S} UTC  app status: {ssm('orders-app status').splitlines()[0]}")
    print(f"{now():%H:%M:%S} UTC  stopping the DMS task while the app is still writing to the source ...")
    stop_task()
    print(f"{now():%H:%M:%S} UTC  task stopped; the app keeps taking orders for 15 s ...")
    time.sleep(15)
    print(ssm("orders-app stop").strip())
    src, tgt = counts("source"), counts("aurora")
    print(f"\n{now():%H:%M:%S} UTC  after the 'cutover':")
    show_counts(src, tgt)
    lost = src[2] - tgt[2]
    print(f"\nIf the app had been pointed at Aurora now, {lost} orders and {src[3] - tgt[3]} order lines taken in the "
          f"last moments on the source would never have existed on Aurora.")
    os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
    with open(os.path.join(ROOT, "build", "premature-cutover.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["table", "source", "aurora", "missing"])
        for name, s, t in zip(TABLES, src, tgt):
            w.writerow([name, s, t, s - t])
    print("saved build/premature-cutover.csv")


def run():
    t = aws("dms", "describe-replication-tasks", "--filters", f"Name=replication-task-arn,Values={env('TASK_ARN')}")["ReplicationTasks"][0]
    if t["Status"] != "running":
        sys.exit(f"the DMS task is {t['Status']}, not running: resume it first")
    marks = {}
    print("CUTOVER\n")
    print(f"{now():%H:%M:%S} UTC  1. stopping the application (orders stop being taken)")
    print("    " + ssm("orders-app stop").strip().replace("\n", "\n    "))
    marks["app_stopped"] = now()

    print(f"{now():%H:%M:%S} UTC  2. gate: Aurora row counts equal the source")
    t0 = time.time()
    while True:
        src, tgt = counts("source"), counts("aurora")
        if src == tgt:
            show_counts(src, tgt)
            break
        if time.time() - t0 > 600:
            return rollback("counts still differ after 10 minutes", src, tgt)
        print(f"    still catching up: source orders {src[2]:,} / aurora {tgt[2]:,}", flush=True)
        time.sleep(5)
    marks["caught_up"] = now()

    print(f"{now():%H:%M:%S} UTC  3. gate: DMS validation complete (every table Validated, 0 pending, 0 failed)")
    t0 = time.time()
    while True:
        ts = table_stats()
        pend = sum(x.get("ValidationPendingRecords", 0) for x in ts)
        fail = sum(x.get("ValidationFailedRecords", 0) for x in ts)
        susp = sum(x.get("ValidationSuspendedRecords", 0) for x in ts)
        states = {x["TableName"]: x.get("ValidationState") for x in ts}
        if fail:
            return rollback(f"{fail} records failed validation", src, tgt)
        if susp:
            return rollback(f"{susp} records could not be validated (suspended)", src, tgt)
        if pend == 0 and all(v == "Validated" for v in states.values()):
            print(f"    {', '.join(f'{k}: {v}' for k, v in sorted(states.items()))}")
            break
        if time.time() - t0 > 900:
            return rollback(f"validation still pending ({pend}) after 15 minutes", src, tgt)
        print(f"    validation pending {pend}  {sorted(set(states.values()))}", flush=True)
        time.sleep(10)
    marks["validated"] = now()

    print(f"{now():%H:%M:%S} UTC  4. stopping the DMS task")
    stop_task()
    marks["task_stopped"] = now()

    print(f"{now():%H:%M:%S} UTC  5. adding the foreign keys on Aurora")
    sql = open(os.path.join(ROOT, "sql", "add-foreign-keys.sql")).read()
    try:
        print("    " + ssm(f"retail-db sql aurora <<'EOSQL'\n{sql}\nEOSQL").strip().replace("\n", "\n    "))
    except RuntimeError as e:
        print(f"\nFOREIGN KEYS FAILED (a reference on Aurora is broken):\n{e}")
        aws("dms", "start-replication-task", "--replication-task-arn", env("TASK_ARN"),
            "--start-replication-task-type", "resume-processing")
        return rollback("foreign keys could not be added; DMS task resumed", src, tgt)
    marks["fks_added"] = now()

    print(f"{now():%H:%M:%S} UTC  6. starting the application against Aurora")
    try:
        print("    " + ssm("orders-app start aurora").strip().replace("\n", "\n    "))
    except RuntimeError as e:
        print(f"\nTHE APP DID NOT START ON AURORA:\n{e}")
        print("Aurora has the data and the foreign keys; the DMS task is stopped. Starting the app on the source again.")
        print(ssm("orders-app start source").strip())
        sys.exit(1)
    time.sleep(8)
    last_src, first_aur = app_log_times()
    if not first_aur:
        print("\nNo successful write to Aurora in the log yet. Check: orders-app log 20")
        return
    down = (first_aur - last_src).total_seconds()
    print(f"\nlast order on the source  {last_src:%H:%M:%S.%f}"[:-3] + " UTC")
    print(f"first order on Aurora     {first_aur:%H:%M:%S.%f}"[:-3] + " UTC")
    print(f"DOWNTIME (no orders taken): {down:.1f} s")
    steps = [("catch-up (counts equal)", "app_stopped", "caught_up"), ("validation gate", "caught_up", "validated"),
             ("stop DMS task", "validated", "task_stopped"), ("add foreign keys", "task_stopped", "fks_added")]
    for label, a, b in steps:
        print(f"    {label:<26} {(marks[b] - marks[a]).total_seconds():6.1f} s")
    os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
    with open(os.path.join(ROOT, "build", "cutover-results.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["last_source_write_utc", "first_aurora_write_utc", "downtime_s"] + [s[0] for s in steps])
        w.writerow([last_src.isoformat(), first_aur.isoformat(), f"{down:.1f}"] +
                   [f"{(marks[b] - marks[a]).total_seconds():.1f}" for _, a, b in steps])
    print("saved build/cutover-results.csv")


def rollback(reason, src, tgt):
    print(f"\nGATE NOT MET: {reason}")
    show_counts(src, tgt)
    print("ROLLBACK: restarting the application on the source; the DMS task keeps running. Nothing was cut over.")
    print(ssm("orders-app start source").strip())
    sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("premature", "run"):
        sys.exit(__doc__)
    premature() if sys.argv[1] == "premature" else run()
