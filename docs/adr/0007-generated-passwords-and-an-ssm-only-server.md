# ADR 0007: Every password generated into one secret; the server managed only through SSM

**Status:** Accepted
**Context:** A migration touches five database accounts on three engines, and DMS endpoints need passwords too.
Typed or copied passwords end up in shell history, screenshots and chat.

## Options considered

| Option | Verdict |
|---|---|
| Passwords chosen and typed by hand | ❌ Weak, reused, and visible in history and screenshots |
| One secret per account | ⚠️ Fine, but five secrets to manage for a short-lived migration |
| **One Secrets Manager secret holding five generated passwords, read only inside `$( ... )`** | ✅ Chosen |

## Decision

[`scripts/secret.py`](../../scripts/secret.py) generates five 28-character passwords (letters and digits only, so
no shell, SQL or connection string can misread them) and stores them as one JSON secret. Commands read a
password inside `$( ... )` at the moment of use; the server's tools read it from Secrets Manager the same way. The
server's role can read only that secret and use SSM. Every command on the server runs through SSM Run Command:
no SSH, no key pair, no inbound port except MySQL from DMS.

## Consequences

- No password appears in any screenshot, file or command in this repo; `secret.py keys` shows names and lengths only.
- On the server, MySQL's root password is handed to the container as an environment variable, which Docker keeps in
  the container's settings. That's acceptable for a lab host only reachable through SSM; in production the database
  would be configured without it.
- The DMS endpoints hold their own copy of the password; in production I'd point them at Secrets Manager
  directly so a rotation doesn't need endpoint changes.
- The secret is force-deleted at teardown, because the passwords die with the databases.
