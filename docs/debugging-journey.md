# Debugging journey

The two trap drills failed on purpose ([`trap-drills.md`](trap-drills.md)). These are the things that surprised
me along the way, and what each one taught me.

---

## 1 · The error message named the symptom; the log named the cause

When trap 1 failed, the task reported only this ([`13`](screenshots/13-step7-trap1-task-failed.png)):

```
TASK FAILED: Last Error  Failed in resolving configuration. Stop Reason FATAL_ERROR Error Level FATAL
```

"Resolving configuration" could mean a dozen things. The cause was in the task's CloudWatch log group,
`dms-tasks-retail-dms`, which exists because logging is on in the task settings and `dms-cloudwatch-logs-role`
lets DMS write there.

My first search of that log returned nothing at all:

```bash
aws logs filter-log-events --log-group-name dms-tasks-retail-dms --filter-pattern '"binary logging"' ...
```

CloudWatch Logs filter patterns are case-sensitive, and DMS writes `Binary Logging`. Rather than guess the
capitalisation, I pulled the messages and searched them myself:

```bash
aws logs filter-log-events --log-group-name dms-tasks-retail-dms --query 'events[].message' --output text \
  | tr '\t' '\n' | grep -iE 'binary|binlog|\]E:' | head -20
```

`--output text` puts the messages on one line separated by tabs, `tr` splits them back into lines, and
`grep -i` ignores case. The `]E:` pattern catches every line DMS tags as an error. The answer was there, right after DMS connected to the source
([`14`](screenshots/14-step7-trap1-task-log.png)): `Binary Logging must be enabled for MySQL server`.

**Lesson:** for DMS, the task status says *that* it failed; the task log says *why*. And when a search returns
nothing, first check whether the search itself can be trusted.

---

## 2 · A connection test that passed, for a task that couldn't work

The source endpoint tested `successful` with the binary log off
([`12`](screenshots/12-step6-connection-tests.png)). The test proves the replication instance can reach MySQL
and log in with `dms_user`. CDC's requirements (binary logging and its format) are only checked when a task
starts.

**Lesson:** "connection successful" is a network-and-credentials check, not a readiness check. DMS
premigration assessments are the place to check source settings like this before a task ever runs.

---

## 3 · `--query` printed `None`, then the answer twice

Checking where dms.t3.medium is offered ([`01`](screenshots/01-step0-availability-and-aurora-version.png)):

```
aws dms describe-orderable-replication-instances --query 'OrderableReplicationInstances[?ReplicationInstanceClass==`dms.t3.medium`] | [0].AvailabilityZones' --output text
None
us-east-1a      us-east-1b      us-east-1c      us-east-1d      us-east-1e      us-east-1f
us-east-1a      us-east-1b      us-east-1c      us-east-1d      us-east-1e      us-east-1f
```

The AWS CLI fetches long lists in pages. With text output, it applies `--query` to each page separately: on one
page there was no dms.t3.medium entry, so `[0]` was `None`; two other pages each contained an entry for it. The answer (1a to 1f) was right; the shape of the output came
from the paging.

**Lesson:** when a CLI query prints more than one result for something that should be one, think about pages
before thinking about bugs. With JSON output the CLI applies the query once, to the merged result, which removes the doubt.

---

## 4 · Aurora's instance class isn't offered in every AZ

The same check for Aurora ([`01`](screenshots/01-step0-availability-and-aurora-version.png)): db.t4g.medium
for `8.0.mysql_aurora.3.13.0` is offered in us-east-1b, 1c, 1d and 1f, **not 1a**. My DB subnet group spans 1a
and 1b, so 1b was the only subnet the writer could use. One writer was fine. For a reader in a second AZ, both
subnets would have to be in AZs that offer the class, so I'd check this before fixing the subnet layout of a
production cluster.

---

## 5 · The application's log was one order behind the database

In the premature-cutover drill ([`18`](screenshots/18-step9-trap2-premature-cutover.png)) the app's last logged
order was 201,001, but the source's newest order was 201,002. The app writes its log line after the database
confirms the insert, and it was stopped in between. Order 201,002 was real; the log just never heard about it.

**Lesson:** the application's log is the right clock for *downtime* (it's what customers experienced), but the
wrong source for *completeness*. That's why the cutover gates compare the two databases directly.

---

## 6 · DMS's CDC counters look like they restart when a task is resumed

DMS's table statistics after the cutover ([`25`](screenshots/25-step10-app-on-aurora-final-stats.png)) showed
200,147 orders from the full load and 828 CDC inserts, which adds up to 200,975, not the 201,688 orders Aurora
actually had. The difference is exactly the inserts from before the premature-cutover stop: Aurora had 200,860
orders when DMS stopped (713 after the full load), and 200,147 + 713 + 828 = 201,688. Order lines fit the same way
(400,147 + 713 + 828 = 401,688). The numbers fit exactly if the counters started again from zero at `resume-processing`, which is how I read it.

**Lesson:** the statistics are useful for watching a task move, not as evidence that everything arrived.
Evidence is row counts and validation, which is what my gates use.

---

## 7 · Small one: an open quote

Splitting `retail-db users-source` over two lines left a quote open, so bash showed its `>` continuation prompt
and waited ([`07`](screenshots/07-step3-seed-and-users.png)). Ctrl+C and the command on one line fixed it. Every
command I run is one line for exactly this reason.
