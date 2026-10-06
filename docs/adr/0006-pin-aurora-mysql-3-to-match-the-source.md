# ADR 0006: Pin Aurora MySQL 3 (8.0-compatible) to match the source

**Status:** Accepted
**Context:** The source runs MySQL 8.0. Aurora MySQL offers an 8.0-compatible line (version 3) and a newer
8.4-compatible line with different defaults: like MySQL 8.4, it disables `mysql_native_password` by default.

## Options considered

| Option | Verdict |
|---|---|
| Whatever version the CLI defaults to | ❌ Could change between rehearsal and migration night, and could change the major version |
| Aurora MySQL 8.4-compatible | ❌ Two changes at once (platform and major version); `mysql_native_password`, which the application and DMS users here use, is off by default |
| **The latest Aurora MySQL 3 (8.0-compatible) release, pinned** | ✅ Chosen |

## Decision

Look up the newest `8.0.mysql_aurora.3.*` version, save it (`AURORA_VERSION`, here `8.0.mysql_aurora.3.13.0`), and
use it for the cluster and the writer. Users are created with `mysql_native_password`, as on the source.

## Consequences

- One change at a time: platform now, major version later as its own tested upgrade.
- The rehearsal and the real migration use the same version.
- The 8.4 upgrade (and the authentication change that comes with it) goes on the roadmap.
