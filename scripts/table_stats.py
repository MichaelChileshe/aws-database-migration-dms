#!/usr/bin/env python3
"""Per-table DMS statistics: rows loaded, CDC inserts/updates, validation state. Saves build/<label>-tables.csv.

  python3 scripts/table_stats.py <task-arn> <label>
"""
import csv, os, sys
from kit_aws import aws, ROOT

COLS = [("TableName", "table"), ("FullLoadRows", "full load"), ("Inserts", "cdc ins"), ("Updates", "cdc upd"),
        ("Deletes", "cdc del"), ("TableState", "state"), ("ValidationState", "validation"),
        ("ValidationPendingRecords", "pending"), ("ValidationFailedRecords", "failed"),
        ("ValidationSuspendedRecords", "suspended")]


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    arn, label = sys.argv[1], sys.argv[2]
    rows = sorted(aws("dms", "describe-table-statistics", "--replication-task-arn", arn).get("TableStatistics", []),
                  key=lambda r: r["TableName"])
    table = [[str(r.get(k, "")) for k, _ in COLS] for r in rows]
    head = [h for _, h in COLS]
    w = [max(len(x[i]) for x in [head] + table) for i in range(len(head))]
    for line in [head] + table:
        print("  ".join(v.ljust(w[i]) for i, v in enumerate(line)))
    total = sum(r.get("FullLoadRows", 0) for r in rows)
    print(f"\n{len(rows)} tables, {total:,} rows in the full load, "
          f"{sum(r.get('Inserts', 0) for r in rows):,} CDC inserts, {sum(r.get('Updates', 0) for r in rows):,} CDC updates")
    os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
    with open(os.path.join(ROOT, "build", f"{label}-tables.csv"), "w", newline="") as f:
        cw = csv.writer(f)
        cw.writerow(head)
        cw.writerows(table)
    print(f"saved build/{label}-tables.csv")


if __name__ == "__main__":
    main()
