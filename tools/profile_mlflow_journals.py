"""Synthetic-only DELETE/FULL versus PERSIST/FULL observations.

Run with ``python -m tools.profile_mlflow_journals --repeats 4`` for the bounded
hosted comparison; the local default is one fresh worker per mode. This tool
never changes production archive policy and its exit status is not acceptance.
"""
from __future__ import annotations

import argparse
from contextlib import closing, contextmanager, redirect_stderr, redirect_stdout
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time

from tools.profile_mlflow_archive import MARKER, safe_output, verify_committed

POLICY_MARKER = "INVEST_JOURNAL_POLICY "
MAX_STDOUT = 4096
MAX_DIAGNOSTIC_BYTES = 256 * 1024
COUNT_KEYS = frozenset({"sqlite_connections", "matched", "configured", "verified",
                        "unrelated_untouched", "rejected"})
CHECK_KEYS = frozenset({"integrity_ok", "foreign_keys_ok", "schema_head_matches"})
ORDER = ("DELETE", "PERSIST", "PERSIST", "DELETE", "PERSIST", "DELETE", "DELETE", "PERSIST")
CHILD = r'''
import sys
def deny(event,args):
    if event in {'socket.connect','socket.getaddrinfo','socket.sendto','socket.bind'}:
        raise RuntimeError('network disabled for synthetic journal comparison')
sys.addaudithook(deny)
sys.path.insert(0,sys.argv[1])
from tools.profile_mlflow_journals import worker_main
worker_main(sys.argv[2],sys.argv[3])
'''


def case_order(repeats):
    if type(repeats) is not int or not 1 <= repeats <= 4:
        raise ValueError("repeats must be between one and four")
    return ORDER[:2 * repeats]


def empty_counts():
    return {key: 0 for key in sorted(COUNT_KEYS)}


def valid_counts(candidate):
    return (type(candidate) is dict and set(candidate) == COUNT_KEYS
            and all(type(value) is int and 0 <= value <= 10000 for value in candidate.values()))


def check_paths(database):
    """Reject pre-existing redirections before any connection is opened."""
    for path in (database, *(Path(str(database) + suffix) for suffix in ("-journal", "-wal", "-shm"))):
        if path.is_symlink() or path.resolve() != path or (path.exists() and not path.is_file()):
            raise ValueError("invalid synthetic database path")


@contextmanager
def connection_policy(database, mode, counts, snapshot, cleanup=None):
    """Observe/configure only new SQLite connections to the exact temporary DB."""
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    if mode not in {"DELETE", "PERSIST"}:
        raise ValueError("unsupported diagnostic journal mode")
    database = Path(database)
    if not database.is_absolute():
        raise ValueError("absolute synthetic database path required")
    check_paths(database)
    active = True

    def connected(connection, _record):
        if not active or not isinstance(connection, sqlite3.Connection):
            return
        counts["sqlite_connections"] += 1
        try:
            main = [row[2] for row in connection.execute("PRAGMA database_list") if row[1] == "main"]
            if len(main) != 1 or not main[0] or Path(main[0]).resolve() != database:
                counts["unrelated_untouched"] += 1
                snapshot()
                return
            counts["matched"] += 1
            check_paths(database)
            if connection.in_transaction:
                raise ValueError("unexpected diagnostic transaction")
            current = connection.execute("PRAGMA main.journal_mode").fetchone()[0]
            if current not in {"delete", "persist"}:
                raise ValueError("unexpected prior journal mode")
            # Values are closed literals, never user input or a URI option.
            selected = connection.execute("PRAGMA main.journal_mode=" + mode).fetchone()[0]
            connection.execute("PRAGMA main.synchronous=FULL")
            counts["configured"] += 1
            actual_mode = connection.execute("PRAGMA main.journal_mode").fetchone()[0]
            actual_sync = connection.execute("PRAGMA main.synchronous").fetchone()[0]
            if selected != mode.lower() or actual_mode != mode.lower() or actual_sync != 2:
                raise ValueError("diagnostic connection policy rejected")
            counts["verified"] += 1
        except Exception:
            counts["rejected"] += 1
            snapshot()
            raise
        snapshot()

    event.listen(Engine, "connect", connected)
    try:
        yield
    finally:
        active = False
        event.remove(Engine, "connect", connected)
        if cleanup is not None:
            cleanup["removed"] = not event.contains(Engine, "connect", connected)


def database_checks(database):
    """Read-only validation using the official pinned SDK's expected schema head."""
    from mlflow.store.db.utils import _get_latest_schema_revision

    expected = _get_latest_schema_revision()
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=2)) as db:
        return {
            "integrity_ok": db.execute("PRAGMA integrity_check").fetchall() == [("ok",)],
            "foreign_keys_ok": db.execute("PRAGMA foreign_key_check").fetchall() == [],
            "schema_head_matches": db.execute("SELECT version_num FROM alembic_version").fetchall() == [(expected,)],
        }


def worker_main(destination, mode):
    from invest import mlflow_tracking as archive

    started = time.monotonic()
    counts = empty_counts()
    checks = {key: None for key in sorted(CHECK_KEYS)}
    cleanup = {"removed": False}
    archive_returned = False
    os.environ["MLFLOW_DISABLE_TELEMETRY"] = "true"
    os.environ["DO_NOT_TRACK"] = "true"
    os.environ["MLFLOW_ENABLE_ASYNC_LOGGING"] = "false"

    def phase(name):
        if name in archive.ARCHIVE_PHASES:
            print(MARKER + json.dumps({"name": name, "seconds": round(time.monotonic() - started, 4)}),
                  file=sys.__stderr__, flush=True)

    def snapshot():
        print(POLICY_MARKER + json.dumps(counts, sort_keys=True), file=sys.__stderr__, flush=True)

    result = {"status": "failed", "reason": "local_archive_unavailable", "study_saved": True}
    try:
        raw = sys.stdin.buffer.read(archive.MAX_STUDY_BYTES + 1)
        if len(raw) > archive.MAX_STUDY_BYTES:
            raise ValueError("synthetic study exceeds bound")
        root = Path(destination).resolve()
        database = root / "mlflow" / "tracking.sqlite"
        # Check before SQLAlchemy or MLflow can open the database, not merely in
        # the connect callback (which runs after the raw DBAPI open).
        check_paths(database)
        with open(os.devnull, "w") as quiet, redirect_stdout(quiet), redirect_stderr(quiet):
            with connection_policy(database, mode, counts, snapshot, cleanup):
                result = archive._archive_local(json.loads(raw), root, progress=phase)
                archive_returned = True
                checks = database_checks(database)
    except archive.UnsupportedMLflowVersion:
        result["reason"] = "unsupported_mlflow_version"
    except ImportError:
        result["reason"] = "mlflow_extra_required"
    except sqlite3.OperationalError as error:
        result["reason"] = "archive_busy" if archive._sqlite_busy_error(error) else "local_archive_unavailable"
    except Exception:
        # Deliberately retain no SDK exception text, path, SQL or traceback.
        if not archive_returned:
            result = {"status": "failed", "reason": "local_archive_unavailable", "study_saved": True}
    snapshot()
    print(json.dumps({"worker": result, "connection_policy": counts,
                      "checks": checks, "listener_removed": cleanup["removed"]}), flush=True)


def observations(stdout, stderr):
    """Only fixed fields/categories leave the synthetic subprocess boundary."""
    from invest.mlflow_tracking import ARCHIVE_PHASES, WORKER_TIMEOUT

    raw = stdout if len(stdout or b"") <= MAX_STDOUT else b""
    limited = (stderr or b"")[:MAX_DIAGNOSTIC_BYTES]
    try:
        payload, _ = safe_output(raw, b"")
    except (RecursionError, OverflowError):
        payload = {}
    phases = []
    counts = empty_counts()
    for line in limited.decode("utf-8", errors="replace").splitlines():
        if len(line) > 1024:
            continue
        try:
            if line.startswith(POLICY_MARKER):
                candidate = json.loads(line[len(POLICY_MARKER):])
                if valid_counts(candidate):
                    counts = candidate
            elif line.startswith(MARKER) and len(phases) < 100:
                candidate = json.loads(line[len(MARKER):])
                if (type(candidate) is dict and not set(candidate) - {"name", "seconds", "error_type"}
                        and type(candidate.get("name")) is str and candidate["name"] in ARCHIVE_PHASES
                        and type(candidate.get("seconds")) in {int, float}
                        and 0 <= candidate["seconds"] <= WORKER_TIMEOUT):
                    phases.append({"name": candidate["name"], "seconds": candidate["seconds"]})
        except (ValueError, TypeError, RecursionError, OverflowError):
            pass
    if payload:
        # A completed envelope must supply its final counters. Older stderr
        # snapshots are useful for interrupted workers, not final evidence.
        final_counts = payload.get("connection_policy")
        counts = final_counts if valid_counts(final_counts) else empty_counts()
    checks = payload.get("checks", {})
    checks = {key: checks.get(key) if type(checks) is dict and type(checks.get(key)) is bool else None
              for key in sorted(CHECK_KEYS)}
    worker = payload.get("worker", {})
    safe_worker = {}
    if type(worker) is dict:
        status = worker.get("status")
        if type(status) is str and status in {"archived", "failed"}:
            safe_worker["status"] = status
        reason = worker.get("reason")
        if reason is not None:
            allowed = {"archive_busy", "local_archive_unavailable", "unsupported_mlflow_version", "mlflow_extra_required"}
            safe_worker["reason"] = reason if type(reason) is str and reason in allowed else "unrecognized_reason"
        run_id = worker.get("run_id")
        if type(run_id) is str and len(run_id) == 32 and all(c in "abcdef0123456789" for c in run_id):
            safe_worker["run_id"] = run_id
    return safe_worker, phases, counts, checks, payload.get("listener_removed") is True


def run_case(package_root, destination, mode, index, raw):
    from invest.mlflow_tracking import WORKER_TIMEOUT

    started = time.monotonic()
    env = {key: value for key, value in os.environ.items() if not key.startswith("MLFLOW_")}
    env.update(MLFLOW_DISABLE_TELEMETRY="true", DO_NOT_TRACK="true", MLFLOW_ENABLE_ASYNC_LOGGING="false")
    timeout, returncode = False, None
    stdout = stderr = b""
    try:
        # Capture to private temporary files, then read at most cap+1 bytes.
        # This bounds parent memory even if an SDK emits unexpected output.
        # Files are diagnostic scratch, not SQLite journals, and are closed only
        # after run() has reaped the completed or timed-out child.
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            try:
                outcome = subprocess.run([sys.executable, "-I", "-c", CHILD, str(package_root), str(destination), mode],
                    input=raw, stdout=out, stderr=err, env=env, cwd=destination.parent,
                    timeout=WORKER_TIMEOUT, check=False)
                returncode = outcome.returncode
            except subprocess.TimeoutExpired:
                timeout = True
            out.seek(0)
            err.seek(0)
            stdout, stderr = out.read(MAX_STDOUT + 1), err.read(MAX_DIAGNOSTIC_BYTES + 1)
    except OSError:
        pass
    worker, phases, counts, checks, cleaned = observations(stdout, stderr)
    reason = worker.get("reason")
    if reason not in {None, "archive_busy", "local_archive_unavailable", "unsupported_mlflow_version", "mlflow_extra_required"}:
        reason = "unrecognized_reason"
    evidence = verify_committed(destination, worker, raw)
    completed = not timeout and returncode == 0
    truncated = len(stderr or b"") > MAX_DIAGNOSTIC_BYTES or len(stdout or b"") > MAX_STDOUT
    policy_verified = (counts["matched"] > 0
        and counts["matched"] == counts["configured"] == counts["verified"]
        and counts["rejected"] == 0)
    if timeout:
        case_outcome = "timeout"
    elif not completed:
        case_outcome = "process_failed"
    elif worker.get("status") != "archived":
        case_outcome = "archive_failed"
    elif not (not truncated and policy_verified and cleaned and all(value is True for value in checks.values())
              and evidence.get("artifact_matches") is True and evidence.get("database_finished") is True):
        case_outcome = "verification_failed"
    else:
        case_outcome = "archived"
    return {
        "case": index, "mode": mode, "synchronous": "FULL", "synthetic_only": True,
        "deadline_seconds": WORKER_TIMEOUT, "elapsed_seconds": round(time.monotonic() - started, 3),
        "sqlite_version": sqlite3.sqlite_version, "process_timeout": timeout, "returncode": returncode,
        "case_completed": completed, "case_outcome": case_outcome,
        "reported_worker_status": worker.get("status") if worker.get("status") in {"archived", "failed"} else "not_emitted",
        "worker_reason": reason, "phases": phases, "connection_policy": counts,
        "checks": checks, "listener_removed": cleaned,
        "committed_evidence": evidence,
        "diagnostic_output_truncated": truncated,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, choices=range(1, 5), default=1)
    args = parser.parse_args(argv)
    from invest.data import demo_dataset
    from invest.experiments import run_study
    from invest.workspace import Workspace, canonical

    package_root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="invest-journal-profile-") as directory:
        root = Path(directory).resolve()
        record = Workspace(root / "state.sqlite").put("study", run_study(demo_dataset(), {
            "symbol": "600000.SH", "cost_model_acknowledged": True}))
        raw = canonical(record).encode("utf-8")
        for index, mode in enumerate(case_order(args.repeats), 1):
            result = run_case(package_root, root / str(index), mode, index, raw)
            print(json.dumps(result, allow_nan=False), flush=True)
    # Collection failure remains an observation; the full SDK gate is separate.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
