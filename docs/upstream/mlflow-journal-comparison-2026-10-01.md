# Synthetic SQLite journal comparison (2026-10-01)

This is a diagnostic-only comparison for intermittent fresh local MLflow archive
startup deadlines. It does not change Invest's production SQLite settings,
replace MLflow migrations, increase a deadline, or replace the existing full SDK
acceptance workflows.

## Evidence motivating the measurement

On the native-report stack, original head `859191940c7257ef3e5b6bc7087f951026f1b664`
had an initial-archive timeout during `client_initialization`. Diagnostic head
`c093f52e63133f9cd1221d2d1e3db3f2c88c6b0e` reproduced it with last start marker
`schema_upgrade` on Windows Python 3.12 (standalone MLflow) and Python 3.10
(full six-SDK suite). These happened before the relevant artifact adversaries.
The marker includes possible later schema verification/default-experiment work;
it is not a statement-level migration diagnosis. The separate Windows text-mode
probe error was fixed by explicit UTF-8 transport in head
`5a2ab7de29253af750326bf3d11b20da23001b17`.

- [Original deadline failure](https://github.com/Jvust1/Invest/actions/runs/36789951703)
- [Finer standalone observations](https://github.com/Jvust1/Invest/actions/runs/36793183980)
- [Finer coinstalled observations](https://github.com/Jvust1/Invest/actions/runs/36793184075)

## Comparison protocol

Run `python -m tools.profile_mlflow_journals --repeats 4` from the source checkout
with the pinned local MLflow extra. The local default is one fresh worker per
mode; repeats are restricted to 1–4. Hosted Windows Python 3.11 and 3.12 use eight
fresh stores in the order DELETE, PERSIST, PERSIST, DELETE, PERSIST, DELETE,
DELETE, PERSIST. The tool accepts no user-supplied records or account credentials;
it uses only synthetic study data. Non-MLFLOW environment values are inherited
without being printed. It removes private temporary stores only
after the workers have exited or been killed/reaped.

Both arms use the public SQLAlchemy Engine `connect` event, restricted to an
exact resolved temporary tracking database path. Every matching new DBAPI
connection, including the official migration connection, receives and verifies
its assigned journal mode plus `synchronous=FULL`. Unrelated databases are not
changed. The tool does not alter autocommit, isolation or locking mode, issue an
extra commit, or install a production hook. Unexpected existing modes and
redirected database/sidecar paths are rejected. WAL is never enabled.

The actual pinned MLflow 3.16.1 store creates and migrates the database normally.
Each worker retains the same 45-second total subprocess budget and inherited
30-second writer-lock budget. Before imports, the worker rejects socket connect,
DNS, datagram send and bind operations. Telemetry is disabled and inherited
MLFLOW configuration is scrubbed. Binary UTF-8 avoids Windows locale conversion.

An `archived` case requires child exit zero before the deadline, verified policy
on all observed matching connections, removed listener, `integrity_check`,
`foreign_key_check`, the official latest migration revision, exact study artifact
bytes and a FINISHED run read from the database. Timeout/nonzero outcomes remain
failed cases even if the child emitted success or committed an artifact. Only
fixed categories, counts, timings and SQLite version are printed; raw SDK logs,
SQL, filesystem paths, environment values and run IDs are not published.

The tool exits zero to collect all observations. A green diagnostic workflow
means collection ran, not that every archive succeeded. Read the per-case
`case_outcome`, checks and committed evidence. The ordinary complete MLflow and
six-SDK gates are unchanged and remain separate acceptance requirements.

## Interpretation limits

Four cases per mode on a hosted runner are a small comparison, not a reliability
or causal claim. Report all cases, timeout counts and timing distributions,
including overlapping or contradictory results. Warm caches, scheduler load and
filesystem behavior can affect the observations. A Linux one-per-mode smoke test
does not establish a Windows improvement.

PERSIST retains a rollback journal and can retain old page bytes. That privacy
and disk-space tradeoff, interrupted migrations, recovery and concurrency require
separate review before any production adoption. These disposable synthetic
stores contain no private inputs. No journal file is manually deleted while a
worker is live. FULL does not prove power-loss durability on every filesystem.

Official mechanism references: [SQLite atomic commit](https://www.sqlite.org/atomiccommit.html),
[SQLite journal modes](https://www.sqlite.org/pragma.html#pragma_journal_mode),
[SQLAlchemy connect events](https://docs.sqlalchemy.org/en/20/core/events.html#sqlalchemy.events.PoolEvents.connect).
