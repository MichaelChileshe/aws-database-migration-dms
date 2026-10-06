#!/usr/bin/env python3
"""Run a SQL file on the source, Aurora or PostgreSQL, from the on-prem host, through SSM Run Command.

  python3 scripts/ssm_sql.py source|aurora|pg <file.sql>

The file's text is sent inside the command (no copying files around), and retail-db on the host runs it with the
right client, endpoint and password. Output comes back as tables.
"""
import sys
from kit_aws import env
from ssm_run import wait_online, send

TOOL = {"source": "retail-db sql source", "aurora": "retail-db sql aurora", "pg": "retail-db psql"}


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in TOOL:
        sys.exit(__doc__)
    target, path = sys.argv[1], sys.argv[2]
    iid = env("SRC_ID")
    wait_online(iid)
    body = open(path).read().splitlines()
    send(iid, [f"{TOOL[target]} <<'EOSQL'", *body, "EOSQL"], f"{target}: {path}")


if __name__ == "__main__":
    main()
