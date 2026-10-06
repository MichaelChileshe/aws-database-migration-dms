#!/usr/bin/env python3
"""Regenerates docs/architecture.svg + docs/architecture.png using the OFFICIAL AWS Architecture Icons.

The icon pack is not committed (AWS licenses it for diagrams, not redistribution). Download it from
https://aws.amazon.com/architecture/icons/, unzip, then:

    AWS_ICONS_DIR=/path/to/unzipped-icon-package python3 build_architecture.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from awsdiag import Diagram, GREY, INK

CDC, LOAD, PG, APP, TRAP, GOOD = "#0073BB", "#1D8102", "#E07941", "#8C4FFF", "#D13212", "#1D8102"
d = Diagram(1900, 1100)
d.text(40, 40, "Live order database: on-premises MySQL to Amazon Aurora with AWS DMS (full load + CDC), "
               "validation gates and a measured cutover", 19, "bold")
d.text(40, 64, "Ubuntu Retail Group  ·  orders kept arriving throughout  ·  plus a MySQL to PostgreSQL comparison  ·  us-east-1",
       13, "normal", GREY)


def node(key, x, y, title, lines=(), color=INK, size=44):
    d.icon(key, x, y, size)
    d.text(x + size + 10, y + 15, title, 12.5, "bold", color)
    for i, l in enumerate(lines):
        d.text(x + size + 10, y + 32 + i * 15, l, 11, "normal", GREY)


d.group("cloud", 30, 90, 1440, 780, "AWS Cloud")
d.group("region", 50, 135, 1400, 715, "us-east-1")
d.group("vpc", 70, 180, 1360, 500, "retail-mig-vpc  10.100.0.0/16")
d.group("public", 90, 225, 450, 430, "retail-dc-a 10.100.1.0/24 (1a): the simulated data centre")
d.group("private", 600, 225, 810, 430, "retail-data-a 10.100.11.0/24 (1a) + retail-data-b 10.100.12.0/24 (1b): no internet route")

# ---------------------------------------------------------------- data centre
node("client", 110, 300, "orders-app", ["about 3 orders a second, every write logged (UTC)",
                                         "MySQL until 09:59:42, Aurora from 10:04:27"], APP)
node("database", 110, 410, "MySQL 8.0.46 in Docker", ["ubuntu_retail: 605,500 rows seeded",
                                                      "binary log OFF, then ON (ROW, FULL, 1 day)"])
node("ec2_instance", 110, 520, "retail-db-onprem  10.100.1.6", ["t3.small, Amazon Linux 2023",
                                                               "SSM Run Command only: no SSH, no key pair"])
d.text(110, 632, "3306 inbound from the DMS security group only", 11, "bold", GREY)
d.line([(132, 348), (132, 406)], APP, width=2)

# ---------------------------------------------------------------- migration side
node("dms", 640, 300, "retail-dms  dms.t3.medium, engine 3.5.4", ["10.100.12.27, not publicly accessible",
                                                                 "reads the binary log, writes the targets"], CDC, 56)
d.box(640, 382, 415, 150, CDC, fill="#FFFFFF", dashed=True)
d.icon("dms_task", 650, 392, 32)
d.text(690, 412, "Replication tasks", 12, "bold", CDC)
tasks = [("retail-orders-to-aurora", "full load + CDC, validation on"),
         ("retail-validate-only / -2", "compare only: 392 failed, then 0"),
         ("retail-orders-to-postgres", "full load, DMS creates the tables")]
for i, (n, w) in enumerate(tasks):
    y = 448 + i * 28
    d.text(656, y, n, 11.5, "bold")
    d.text(856, y, w, 11, "normal", GREY)
d.text(640, 560, "Table mappings: every table in ubuntu_retail", 11, "normal", GREY)
d.text(640, 578, "Aurora target: tables pre-created, TRUNCATE_BEFORE_LOAD", 11, "normal", GREY)

node("aurora_mysql", 1080, 290, "retail-aurora", ["Aurora MySQL 8.0.mysql_aurora.3.13.0",
                                                  "writer db.t4g.medium, encrypted",
                                                  "3 foreign keys added at cutover"], LOAD, 48)
node("rds_instance", 1080, 500, "retail-pg", ["RDS for PostgreSQL 16, db.t4g.micro",
                                              "SSL required, encrypted",
                                              "tables created by DMS itself"], PG, 48)

# MySQL -> DMS (binlog), DMS -> Aurora, DMS -> PostgreSQL
d.line([(480, 432), (590, 432), (590, 328), (636, 328)], CDC, width=2.4)
d.label(470, 455, "full load + CDC", CDC, 10.5)
d.line([(1020, 314), (1076, 314)], LOAD, width=2.4)
d.line([(1020, 345), (1062, 345), (1062, 524), (1076, 524)], PG, width=2.2)
# app -> Aurora after cutover
d.line([(132, 298), (132, 270), (1104, 270), (1104, 286)], APP, dashed=True, width=2)
d.label(620, 266, "after the cutover: orders-app -> Aurora writer endpoint (3306, SG to SG)", APP, 10.5)

# ---------------------------------------------------------------- regional services
node("secrets", 90, 715, "Secrets Manager", ["retail-migration/db-passwords",
                                             "5 generated passwords, never shown"], INK, 48)
node("ssm", 440, 715, "Systems Manager", ["Run Command: every command on the server",
                                          "and every SQL file"], INK, 48)
node("cw_logs", 790, 715, "CloudWatch Logs", ["dms-tasks-retail-dms: the task log",
                                              "that named the binary-log error"], INK, 48)
node("iam_role", 1110, 715, "IAM roles", ["retail-onprem-role: 1 secret + SSM",
                                          "dms-vpc-role, dms-cloudwatch-logs-role"], INK, 48)

# ---------------------------------------------------------------- cutover timeline
ty = 905
d.text(40, ty, "Cutover downtime, read from the application's own log: 284.8 s", 15, "bold")
d.text(40, ty + 20, "last order on MySQL 09:59:42.417 UTC  ->  first order on Aurora 10:04:27.236 UTC", 12, "normal", GREY)
x0, scale, by = 40, 1420 / 284.8, ty + 40
segs = [(3.6, "#7D8998", ""),
        (11.9, "#1D8102", "count gate: equal on the first check  11.9 s"),
        (197.4, "#00A4A6", "validation gate: every table Validated, 0 pending  197.4 s"),
        (35.7, "#E07941", "stop DMS task  35.7 s"),
        (33.3, "#8C4FFF", "3 foreign keys  33.3 s"),
        (2.9, "#7D8998", "app stop + start  6.5 s (grey, both ends)")]
x = x0
for i, (sec, col, lab) in enumerate(segs):
    w = sec * scale
    d.raw(f'<rect x="{x:.1f}" y="{by}" width="{w:.1f}" height="34" fill="{col}"/>')
    if lab:
        ly = by + 58 + (20 if i % 2 else 0)
        d.raw(f'<path d="M{x + 2:.1f} {by + 34} L{x + 2:.1f} {ly - 12}" stroke="{col}" stroke-width="1.2"/>')
        d.text(x + 6, ly, lab, 11.5, "bold", col)
    x += w

# ---------------------------------------------------------------- results + legend
bx, bby = 1500, 90
d.box(bx, bby, 375, 530, "#D5DBDB", fill="#fff", dashed=False)
d.text(bx + 14, bby + 26, "Measured", 13.5, "bold")
res = [
    ("Trap 1: binary log off", TRAP, ["connection test passed; the task failed", "(118 s check): \"Binary Logging must be",
                                      "enabled for MySQL server\" (task log)"]),
    ("Full load while trading", LOAD, ["605,794 rows, 4 tables at 100% within", "56 s of the restart; CDC applying orders"]),
    ("Trap 2: cut over too early", TRAP, ["DMS stopped, app still writing:", "142 orders + 142 lines never reached Aurora"]),
    ("Validation-only task", CDC, ["392 failed: 284 MISSING_TARGET,", "108 RECORD_DIFF. Resume, re-check: 0"]),
    ("Gated cutover", GOOD, ["counts, validation, stop, 3 FKs, start:", "every gate passed; 284.8 s without orders"]),
    ("After the cutover", APP, ["app on Aurora with 0 FAIL; it was still", "taking orders (id 204,409) at teardown"]),
    ("MySQL to PostgreSQL", PG, ["608,876 rows, all tables Validated, but", "0 FKs, 1 index per table, no defaults;",
                                "the app's INSERT fails: order_id NULL"]),
    ("Teardown", GOOD, ["every clean-check query empty"]),
]
y = bby + 52
for title, c, ls in res:
    d.text(bx + 14, y, title, 12, "bold", c)
    for l in ls:
        y += 17
        d.text(bx + 14, y, l, 11.2)
    y += 24

lx, ly = 1500, 640
d.raw(f'<rect x="{lx}" y="{ly}" width="375" height="150" rx="4" fill="#fff" stroke="#D5DBDB"/>')
d.text(lx + 12, ly + 22, "Legend", 13, "bold")
for i, (c, t, dash) in enumerate([(CDC, "MySQL -> DMS: full load + binary-log CDC", False),
                                  (LOAD, "DMS -> Aurora MySQL (homogeneous)", False),
                                  (PG, "DMS -> PostgreSQL (heterogeneous comparison)", False),
                                  (APP, "application writes (after cutover: dashed)", True)]):
    yy = ly + 46 + i * 26
    d.line([(lx + 12, yy), (lx + 58, yy)], c, dashed=dash)
    d.text(lx + 66, yy + 4, t, 11.5)

here = os.path.dirname(os.path.abspath(__file__))
d.save(os.path.join(here, "..", "architecture.svg"), os.path.join(here, "..", "architecture.png"))
print("wrote docs/architecture.svg and docs/architecture.png")
