# Cost model

## This build (estimate)

| Item | Rate (us-east-1 list price, approx.) | Notes |
|---|---|---|
| DMS replication instance dms.t3.medium, 50 GB storage | ~US$0.08 per hour | the largest hourly item |
| Aurora MySQL writer db.t4g.medium | ~US$0.07 per hour | plus storage and I/O, small at 600,000 rows |
| RDS for PostgreSQL db.t4g.micro, 20 GB gp3 | ~US$0.02 per hour | no automated backups (retention 0) |
| EC2 t3.small (the on-prem server), 20 GB gp3 | ~US$0.02 per hour | |
| Public IPv4 address on the server | US$0.005 per hour | needed for SSM and Docker images in this lab |
| Secrets Manager, 1 secret | US$0.40 per month, prorated | cents |
| CloudWatch Logs (task logs) | per GB ingested | fractions of a cent |
| **Total** | | **about US$1–2 for the day** |

Everything was created, used and deleted in the same session, so each item ran for a few hours at most.
Cost Explorer refreshes at least once every 24 hours; the confirmed figure for 6 October 2026 will be added here.

Left running, the same set costs about US$5 a day, mostly the replication instance and the Aurora writer.

## Running the migration for Ubuntu Retail

| Item | Why it costs |
|---|---|
| Replication instance for the weeks of the migration | full load, then CDC until cutover; size it for the full load, not the trickle of CDC |
| Multi-AZ replication instance (production) | about double; worth it when CDC runs for weeks and an AZ failure would restart the full load |
| The source's binary log | disk on the on-premises server for the retention period |
| VPN or Direct Connect | DMS reads the source across it; a large full load needs the bandwidth or a longer window |
| Aurora from day one of the full load | the target bills while it's being filled, before it takes a single order |

The replication instance is temporary: once the cutover is signed off and the rollback window has passed, the
tasks, endpoints and instance are deleted, and only Aurora remains.
