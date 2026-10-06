#!/usr/bin/env python3
"""Run something on a Linux instance through SSM Run Command, wait for it, and print the output.
No SSH, no key pair, no inbound port: the instance's SSM agent pulls the command.

  python3 scripts/ssm_run.py sh <instance-id> "<shell command>"
  python3 scripts/ssm_run.py file <instance-id> <script.sh>
"""
import json, subprocess, sys, time
from kit_aws import aws


def wait_online(iid, timeout=900):
    t0 = time.time()
    while time.time() - t0 < timeout:
        info = aws("ssm", "describe-instance-information",
                   "--filters", f"Key=InstanceIds,Values={iid}")["InstanceInformationList"]
        if info and info[0]["PingStatus"] == "Online":
            return
        print(f"  waiting for {iid} to register with Systems Manager ...", flush=True)
        time.sleep(15)
    sys.exit(f"{iid} did not come Online in SSM within {timeout // 60} minutes")


def quiet(*args):
    r = subprocess.run(["aws", *args, "--output", "json"], capture_output=True, text=True)
    return json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else None


def send(iid, lines, comment):
    cid = aws("ssm", "send-command", "--instance-ids", iid, "--document-name", "AWS-RunShellScript",
              "--comment", comment[:100], "--parameters", json.dumps({"commands": lines}))["Command"]["CommandId"]
    t0 = time.time()
    while True:
        time.sleep(3)
        res = quiet("ssm", "get-command-invocation", "--command-id", cid, "--instance-id", iid)
        if not res or res["Status"] in ("Pending", "InProgress", "Delayed"):
            continue
        out, err = res.get("StandardOutputContent", "").rstrip(), res.get("StandardErrorContent", "").rstrip()
        print(f"[{iid}] {res['Status']} in {time.time() - t0:.0f} s")
        if out:
            print(out)
        if err:
            print("----- stderr -----\n" + err)
        if res["Status"] != "Success":
            sys.exit(1)
        return


def main():
    if len(sys.argv) != 4 or sys.argv[1] not in ("sh", "file"):
        sys.exit(__doc__)
    action, iid, arg = sys.argv[1:]
    wait_online(iid)
    lines = [arg] if action == "sh" else open(arg).read().splitlines()
    send(iid, lines, arg if action == "sh" else f"run {arg}")


if __name__ == "__main__":
    main()
