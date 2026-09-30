"""Optional MLflow tracking bridge for reproducible Invest research.

Upstream: mlflow/mlflow @
7faf28476bddcebb68ee8b08cdcba1bee7ad6109 (Apache-2.0).
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Mapping


class MLflowExperimentTracker:
    def __init__(self, mlflow_module: Any, *, experiment_name: str = "Invest") -> None:
        for name in ("set_experiment", "start_run", "log_params", "log_metrics", "set_tags"):
            if not callable(getattr(mlflow_module, name, None)):
                raise TypeError(f"mlflow module must provide {name}()")
        self._mlflow = mlflow_module
        self.experiment_name = str(experiment_name).strip() or "Invest"

    def track(
        self,
        *,
        run_name: str,
        params: Mapping[str, Any] | None = None,
        metrics: Mapping[str, float] | None = None,
        tags: Mapping[str, Any] | None = None,
    ) -> Any:
        self._mlflow.set_experiment(self.experiment_name)
        with self._mlflow.start_run(run_name=str(run_name).strip() or None) as run:
            if params:
                self._mlflow.log_params(dict(params))
            if metrics:
                self._mlflow.log_metrics({str(k): float(v) for k, v in metrics.items()})
            if tags:
                self._mlflow.set_tags({str(k): str(v) for k, v in tags.items()})
            return run


def create_mlflow_tracker(*, experiment_name: str = "Invest") -> MLflowExperimentTracker:
    try:
        import mlflow
    except ImportError as exc:
        raise RuntimeError(
            "MLflow is optional; install Invest with the 'mlflow' extra before enabling tracking"
        ) from exc
    return MLflowExperimentTracker(mlflow, experiment_name=experiment_name)


# The workbench uses this isolated local archive, not the legacy fluent adapter.
# It is a derivative index: the immutable Workspace record remains authoritative.
LOCAL_EXPERIMENT = "Invest workbench studies"
TESTED_MLFLOW_VERSION = "3.16.1"


class UnsupportedMLflowVersion(RuntimeError):
    """The opt-in archive requires its validated SDK version."""
MAX_STUDY_BYTES = 8 * 1024 * 1024 + 4096
WORKER_TIMEOUT = 45
# Leave time for another process's cold schema setup or artifact commit, while
# retaining the outer 45-second hard deadline for every worker.
ARCHIVE_LOCK_TIMEOUT = 30
# Fixed diagnostic vocabulary only. The journal never contains study data,
# filesystem paths, SDK exceptions, environment values or run identifiers.
ARCHIVE_PHASES = frozenset({
    "worker_start", "input_read", "record_validation", "path_validation",
    "sdk_import", "lock_wait", "client_initialization", "experiment_lookup",
    "run_lookup", "artifact_validation", "index_write", "artifact_write",
    "commit", "archive_returned", "response_write", "response_written",
    "sdk_store_import", "initial_tables", "schema_upgrade", "engine_retry",
})


def _write_archive_phase(path, phase):
    if not isinstance(phase, str) or phase not in ARCHIVE_PHASES:
        return
    try:
        with open(path, "w", encoding="ascii") as journal:
            journal.write(phase)
    except (OSError, ValueError):
        # Diagnostic IO must not turn a successful archive into a failure.
        pass


def _read_archive_phase(path):
    try:
        with open(path, "rb") as journal:
            value = journal.read(65).decode("ascii")
        return value if value in ARCHIVE_PHASES else None
    except (OSError, ValueError, UnicodeError):
        return None


@contextmanager
def _archive_phase_journal():
    from pathlib import Path
    import tempfile

    directory = None
    try:
        directory = tempfile.TemporaryDirectory(prefix="invest-archive-phase-",
                                                ignore_cleanup_errors=True)
    except OSError:
        pass
    try:
        if directory is None:
            yield None
        else:
            journal = Path(directory.name) / "phase"
            _write_archive_phase(journal, "worker_start")
            yield journal
    finally:
        if directory is not None:
            try:
                directory.cleanup()
            except OSError:
                pass


@contextmanager
def _initialization_phases(progress):
    """Observe exact pinned-SDK log templates without formatting private args."""
    logger = handler = None
    active = True
    if progress is not None:
        try:
            import logging

            class PhaseHandler(logging.Handler):
                def emit(self, record):
                    try:
                        if not active or record.name != "mlflow.store.db.utils" or type(record.msg) is not str:
                            return
                        phases = {
                            "Creating initial MLflow database tables...": "initial_tables",
                            "Updating database tables": "schema_upgrade",
                            "SQLAlchemy engine could not be created. The following exception is caught.\n"
                            "%s\nOperation will be retried in %.1f seconds": "engine_retry",
                        }
                        phase = phases.get(record.msg)
                        if phase is not None:
                            _mark_archive_phase(progress, phase)
                    except Exception:
                        # No formatting of args, SQL, errors, paths or traceback.
                        pass

            logger = logging.getLogger("mlflow.store.db.utils")
            handler = PhaseHandler()
            logger.addHandler(handler)
        except Exception:
            # Diagnostics may be unavailable, but archival must still proceed.
            pass
    try:
        yield
    finally:
        # Disable observation before best-effort removal, including a failing
        # logger implementation that leaves the handler attached.
        active = False
        if logger is not None and handler is not None:
            try:
                logger.removeHandler(handler)
            except Exception:
                pass
            try:
                handler.close()
            except Exception:
                pass


def _mark_archive_phase(progress, phase):
    if progress is not None and isinstance(phase, str) and phase in ARCHIVE_PHASES:
        try:
            progress(phase)
        except Exception:
            pass


STUDY_MODES = {
    "invest-exploratory-study-v1": "EXPLORATORY_CHRONOLOGICAL_SLICES",
    "invest-walk-forward-study-v1": "EXPLORATORY_WALK_FORWARD",
}


def _checked_record(record: dict) -> bytes:
    import re
    from .workspace import canonical, digest

    if not isinstance(record, dict) or set(record) != {"id", "kind", "recorded_at", "payload"}:
        raise ValueError("invalid saved study record")
    payload = record["payload"]
    if (record["kind"] != "study" or not isinstance(payload, dict)
            or set(payload) != {"schema", "protocol", "protocol_id", "results", "summary", "source_kind", "limitations"}
            or payload["schema"] not in STUDY_MODES
            or record["id"] != digest({"kind": "study", "payload": payload})):
        raise ValueError("saved study identity mismatch")
    protocol = payload["protocol"]
    if (not isinstance(protocol, dict)
            or protocol.get("schema") != payload["schema"]
            or protocol.get("mode") != STUDY_MODES[payload["schema"]]
            or payload["protocol_id"] != digest(protocol)
            or protocol.get("frozen_holdout_opened") is not False):
        raise ValueError("study protocol identity mismatch")
    for key in ("dataset_id", "code_identity"):
        if not isinstance(protocol.get(key), str) or not re.fullmatch("[a-f0-9]{64}", protocol[key]):
            raise ValueError("study input or code identity missing")
    if not isinstance(payload["results"], list) or not 1 <= len(payload["results"]) <= 27:
        raise ValueError("study outcomes exceed the bounded archive contract")
    raw = canonical(record).encode("utf-8")
    if len(raw) > MAX_STUDY_BYTES:
        raise ValueError("saved study exceeds archive limit")
    return raw


def _inside(path, root):
    from pathlib import Path

    resolved = Path(path).resolve()
    # UNC/network shares are not a local archive, including on Windows.
    if str(resolved).startswith(("//", "\\\\")) or not resolved.is_relative_to(root):
        raise ValueError("archive path is outside the configured local root")
    return resolved


def _artifact_path(uri, root):
    from pathlib import Path
    from urllib.parse import urlsplit
    from urllib.request import url2pathname

    parsed = urlsplit(uri)
    if parsed.scheme != "file" or parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("archive artifacts require an absolute local file URI")
    path = Path(url2pathname(parsed.path))
    if not path.is_absolute():
        raise ValueError("archive artifact path must be absolute")
    return _inside(path, root)


def _indexed_values(study):
    """Bounded metrics are local case indices, always paired with a descriptor."""
    import math
    from .workspace import canonical

    protocol = study["protocol"]
    params = {"symbol": protocol["symbol"], "initial_cash": str(protocol["initial_cash"]),
              "mode": protocol["mode"], "parameter_budget": str(protocol["parameter_budget"]),
              "shared_warmup": str(protocol["shared_warmup"]),
              "case_index_scope": "this_protocol_only; compare_descriptors_before_comparing_metrics"}
    for key in ("candidates", "costs", "periods", "folds", "configuration"):
        if key in protocol:
            params[key] = canonical(protocol[key])
    metrics = {"summary." + key: float(study["summary"][key])
               for key in ("planned", "succeeded", "failed", "below_buy_hold")}
    for index, case in enumerate(study["results"]):
        prefix = f"case.{index:03d}."
        descriptor = {key: case[key] for key in
                      ("period", "candidate", "cost", "fold", "train_window", "test_window") if key in case}
        if case["status"] == "PASS":
            result = case["result"]
            descriptor.update(evaluation_start=result["evaluation_start"], evaluation_end=result["evaluation_end"])
            for key in ("total_return", "benchmark_return", "max_drawdown", "total_fees", "benchmark_total_fees"):
                metrics[prefix + key] = float(result["metrics"][key])
        metrics[prefix + "passed"] = float(case["status"] == "PASS")
        params[prefix + "descriptor"] = canonical(descriptor)
    if any(len(value) > 6000 for value in params.values()) or not all(math.isfinite(x) for x in metrics.values()):
        raise ValueError("archive indexed values exceed limits")
    return params, metrics


def _sqlite_busy_error(error):
    """Support Python 3.10 as well as the structured codes added in 3.11."""
    code = getattr(error, 'sqlite_errorcode', None)
    if type(code) is int:
        # Stable SQLite primary result codes: BUSY=5, LOCKED=6. Python 3.10
        # does not expose the corresponding module constants or error attrs.
        return (code & 255) in (5, 6)
    message = str(error)
    return (message in {'database is locked', 'database table is locked'}
            or message.startswith('database table is locked: '))


class LocalMLflowArchive:
    """Opt-in SDK worker with no remote endpoint or global active-run state.

    Each bounded source-Python subprocess exits after synchronous logging, so
    MLflow's cached SQLite engines cannot retain handles in the web server.
    The frozen portable app does not embed this optional SDK worker.
    """

    def __init__(self, data_dir):
        from pathlib import Path
        self.data_dir = Path(data_dir).resolve()

    def archive(self, record: dict) -> dict:
        import json
        import os
        from pathlib import Path
        import subprocess
        import sys

        try:
            raw = _checked_record(record)
            if getattr(sys, "frozen", False):
                return {"status": "failed", "reason": "source_python_required", "study_saved": True}
            # Do not inherit a remote tracking/registry URI, async/telemetry switch,
            # plugin settings, or any other MLflow environment configuration.
            env = {key: value for key, value in os.environ.items() if not key.startswith("MLFLOW_")}
            env.update(MLFLOW_DISABLE_TELEMETRY="true", DO_NOT_TRACK="true",
                       MLFLOW_ENABLE_ASYNC_LOGGING="false")
            bootstrap = ("import sys; sys.path.insert(0, sys.argv[1]); "
                         "from invest.mlflow_tracking import _worker_main; "
                         "_worker_main(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)")
            # Only fixed phase names go into this private temporary journal.
            # Read it after the timed-out child has been killed/reaped by run();
            # never interpret a pre-exit success response as committed success.
            with _archive_phase_journal() as journal:
                command = [sys.executable, "-I", "-c", bootstrap,
                           str(Path(__file__).resolve().parent.parent), str(self.data_dir)]
                if journal is not None:
                    command.append(str(journal))
                try:
                    result = subprocess.run(
                        command,
                        input=raw, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                        env=env, timeout=WORKER_TIMEOUT, check=False,
                    )
                except subprocess.TimeoutExpired:
                    status = {"status": "failed", "reason": "archive_timeout", "study_saved": True}
                    phase = None if journal is None else _read_archive_phase(journal)
                    if phase is not None:
                        status["phase"] = phase
                    return status
            if result.returncode or len(result.stdout) > 4096:
                raise RuntimeError("archive worker did not finish")
            status = json.loads(result.stdout)
            if not isinstance(status, dict) or status.get("status") not in {"archived", "failed"}:
                raise RuntimeError("invalid archive worker response")
            return status
        except subprocess.TimeoutExpired:
            return {"status": "failed", "reason": "archive_timeout", "study_saved": True}
        except Exception:
            # Never reflect SDK errors, filesystem paths, or environment values.
            return {"status": "failed", "reason": "local_archive_unavailable", "study_saved": True}


def _archive_local(record, data_dir, *, progress=None):
    """Worker implementation. The SDK is imported only after the local guards."""
    from contextlib import closing
    from datetime import datetime
    import os
    from pathlib import Path
    import sqlite3

    _mark_archive_phase(progress, "record_validation")
    raw = _checked_record(record)
    _mark_archive_phase(progress, "path_validation")
    root_parent = Path(data_dir).resolve()
    if any(c in str(root_parent) for c in "?#\0"):
        raise ValueError("archive directory cannot contain SQLite URI delimiters")
    root = _inside(root_parent / "mlflow", root_parent)
    root.mkdir(parents=True, exist_ok=True)
    artifacts = _inside(root / "artifacts", root)
    artifacts.mkdir(exist_ok=True)
    database = _inside(root / "tracking.sqlite", root)
    lock_path = _inside(root / "archive-lock.sqlite", root)
    # Set, rather than setdefault: a hostile/inherited false value must not win.
    os.environ["MLFLOW_DISABLE_TELEMETRY"] = "true"
    os.environ["DO_NOT_TRACK"] = "true"
    _mark_archive_phase(progress, "sdk_import")
    from importlib.metadata import version
    if version("mlflow") != TESTED_MLFLOW_VERSION:
        raise UnsupportedMLflowVersion("install the validated local archive extra")
    from mlflow import MlflowClient
    from mlflow.entities import Metric, Param, ViewType
    from mlflow.telemetry import get_telemetry_client

    if get_telemetry_client() is not None:
        raise RuntimeError("MLflow telemetry is not disabled")
    # These official modules are required by the fixed SQLite backend anyway.
    # Separate their lazy import from database initialization and do it before
    # taking the cross-process writer lock; no store/connection is created here.
    _mark_archive_phase(progress, "sdk_store_import")
    from importlib import import_module
    import_module("mlflow.store.db.utils")
    import_module("mlflow.store.tracking.sqlalchemy_store")
    import_module("mlflow.store.tracking.sqlalchemy_workspace_store")
    uri = "sqlite:///" + database.as_posix()
    # An independent SQLite transaction serializes separate server processes.
    # The SDK writes to its own DB, not to this lock database or Workspace.
    _mark_archive_phase(progress, "lock_wait")
    with closing(sqlite3.connect(lock_path, timeout=ARCHIVE_LOCK_TIMEOUT)) as lock:
        lock.execute("BEGIN IMMEDIATE")
        _mark_archive_phase(progress, "client_initialization")
        with _initialization_phases(progress):
            client = MlflowClient(tracking_uri=uri, registry_uri=uri)
        _mark_archive_phase(progress, "experiment_lookup")
        experiment = client.get_experiment_by_name(LOCAL_EXPERIMENT)
        if experiment is None:
            experiment = client.get_experiment(client.create_experiment(
                LOCAL_EXPERIMENT, artifact_location=artifacts.as_uri()))
        if experiment.lifecycle_stage != "active":
            raise ValueError("archive experiment is inactive")
        if _artifact_path(experiment.artifact_location, artifacts) != artifacts:
            raise ValueError("archive experiment artifact directory mismatch")
        study = record["payload"]
        protocol = study["protocol"]
        tags = {"invest.study_id": record["id"], "invest.protocol_id": study["protocol_id"],
                "invest.dataset_id": protocol["dataset_id"], "invest.code_identity": protocol["code_identity"],
                "invest.code_identity_scheme": protocol["code_identity_scheme"],
                "invest.archive_schema": "invest-local-mlflow-v1", "invest.frozen_holdout_opened": "false"}
        params, metric_values = _indexed_values(study)
        _mark_archive_phase(progress, "run_lookup")
        runs = client.search_runs([experiment.experiment_id],
            filter_string=f"tags.`invest.study_id` = '{record['id']}'",
            run_view_type=ViewType.ALL, max_results=2)
        if len(runs) > 1:
            raise ValueError("multiple archive runs have the same study identity")
        if runs:
            run = runs[0]
            if run.info.lifecycle_stage != "active" or any(run.data.tags.get(k) != v for k, v in tags.items()):
                raise ValueError("archive run identity mismatch")
        else:
            run = client.create_run(experiment.experiment_id, tags=tags,
                                    run_name="study-" + record["id"][:16])
        _mark_archive_phase(progress, "artifact_validation")
        run_id = run.info.run_id
        path = _artifact_path(run.info.artifact_uri, artifacts)
        if path != artifacts / run_id / "artifacts":
            raise ValueError("archive run artifact directory mismatch")
        artifact = _inside(path / "study.json", path)
        if artifact != path / "study.json":
            raise ValueError("archive artifact cannot be a symbolic link")
        if run.info.status == "FINISHED":
            if (any(run.data.params.get(k) != v for k, v in params.items())
                    or any(run.data.metrics.get(k) != v for k, v in metric_values.items())):
                raise ValueError("completed archive indexed values mismatch")
            # No duplicate metrics/artifacts for a committed retry. Confirm the
            # archived bytes rather than trusting a stale success status alone.
            if not artifact.is_file() or artifact.stat().st_size > MAX_STUDY_BYTES:
                raise ValueError("completed archive artifact is missing or oversized")
            import json
            if _checked_record(json.loads(artifact.read_bytes())) != raw:
                raise ValueError("completed archive artifact identity mismatch")
            return {"status": "archived", "run_id": run_id, "reused": True, "study_saved": True}
        try:
            # Deterministic timestamps make retries of a partial write idempotent.
            timestamp = int(datetime.fromisoformat(record["recorded_at"]).timestamp() * 1000)
            metrics = [Metric(key, value, timestamp, 0) for key, value in metric_values.items()]
            # Partial failures can be retried without duplicate metric history.
            for metric in metrics:
                if metric.key in run.data.metrics and run.data.metrics[metric.key] != metric.value:
                    raise ValueError("archive summary metrics differ from the saved study")
            metrics = [m for m in metrics if m.key not in run.data.metrics]
            _mark_archive_phase(progress, "index_write")
            client.log_batch(run_id, params=[Param(k, v) for k, v in params.items()],
                             metrics=metrics, synchronous=True)
            # Fetch current metadata again immediately before artifact IO. Never
            # trust remote URLs or paths moved outside the local artifact root.
            if _artifact_path(client.get_experiment(experiment.experiment_id).artifact_location, artifacts) != artifacts:
                raise ValueError("archive experiment artifact directory changed")
            current = client.get_run(run_id)
            current_path = _artifact_path(current.info.artifact_uri, artifacts)
            if current_path != path:
                raise ValueError("archive artifact location changed")
            if _inside(current_path / "study.json", path) != artifact:
                raise ValueError("archive artifact file changed")
            _mark_archive_phase(progress, "artifact_write")
            client.log_text(run_id, raw.decode("utf-8"), "study.json")
            if artifact.read_bytes() != raw:
                raise ValueError("archive artifact write did not match the saved study")
            _mark_archive_phase(progress, "commit")
            client.set_terminated(run_id, status="FINISHED")
            if client.get_run(run_id).info.status != "FINISHED":
                raise RuntimeError("archive did not finish")
        except Exception:
            client.set_terminated(run_id, status="FAILED")
            raise
        return {"status": "archived", "run_id": run_id, "reused": False, "study_saved": True}


def _worker_main(data_dir, phase_path=None):
    import contextlib
    import json
    import os
    import sqlite3
    import sys

    # Defense in depth: this worker has no legitimate socket operations. This
    # audit guard is not an OS sandbox; it also catches accidental SDK telemetry.
    def deny_network(event, args):
        if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto", "socket.bind"}:
            raise RuntimeError("network disabled for the local MLflow archive")

    sys.addaudithook(deny_network)
    progress = None if phase_path is None else lambda name: _write_archive_phase(phase_path, name)
    _mark_archive_phase(progress, "input_read")
    raw = sys.stdin.buffer.read(MAX_STUDY_BYTES + 1)
    try:
        if len(raw) > MAX_STUDY_BYTES:
            raise ValueError("study exceeds archive limit")
        with open(os.devnull, "w") as quiet, contextlib.redirect_stdout(quiet), contextlib.redirect_stderr(quiet):
            if progress is None:
                result = _archive_local(json.loads(raw), data_dir)
            else:
                result = _archive_local(json.loads(raw), data_dir, progress=progress)
            _mark_archive_phase(progress, "archive_returned")
    except UnsupportedMLflowVersion:
        result = {"status": "failed", "reason": "unsupported_mlflow_version", "study_saved": True}
    except ImportError:
        result = {"status": "failed", "reason": "mlflow_extra_required", "study_saved": True}
    except sqlite3.OperationalError as exc:
        # Do not echo filesystem/SDK details. Distinguish retryable writer
        # contention from unrelated local failures, including extended codes.
        busy = _sqlite_busy_error(exc)
        result = {"status": "failed", "reason": "archive_busy" if busy else "local_archive_unavailable",
                  "study_saved": True}
    except Exception:
        result = {"status": "failed", "reason": "local_archive_unavailable", "study_saved": True}
    _mark_archive_phase(progress, "response_write")
    sys.stdout.write(json.dumps(result, separators=(",", ":")))
    sys.stdout.flush()
    _mark_archive_phase(progress, "response_written")
