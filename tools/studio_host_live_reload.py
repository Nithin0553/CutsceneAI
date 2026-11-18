"""Safe local Studio *host* source-change monitor; does not touch game editors.

The Unreal/Unity companions independently remain connected via their persistent
file queues. On an idle, syntax-valid Python update, the launcher can replace
only this localhost Python server process (exit 75). Native jobs and immutable
candidate records are never resubmitted by this watcher.
"""
from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

RELOAD_EXIT_CODE = 75
DIRECTORIES = ("tools", "packages/studio", "packages/cinetwin",
               "packages/learning", "integrations/unreal")
MAX_FILES = 750
MAX_BYTES = 4 * 1024 * 1024
IN_PROGRESS_STAGES = {"CONNECTING", "ANALYZING_PROJECTS", "PREPARING", "UNREAL_RUNNING"}
NATIVE_IN_FLIGHT = {"QUEUED", "RUNNING"}


class HostReloadError(ValueError):
    """Cannot safely determine whether source code changed."""


def source_snapshot(root: Path) -> dict[str, str]:
    """Hash only bounded, trusted host Python files; do not execute them."""
    snapshot = {}
    for directory in DIRECTORIES:
        folder = root / directory
        if folder.is_symlink() or not folder.is_dir():
            raise HostReloadError("Studio live-reload source folder is invalid: " + directory)
        for file in sorted(folder.glob("*.py")):
            if len(snapshot) >= MAX_FILES or file.is_symlink() or not file.is_file():
                raise HostReloadError("Studio live-reload source inventory is unsafe.")
            if not 0 <= file.stat().st_size <= MAX_BYTES:
                raise HostReloadError("Studio live-reload source file is empty or oversized.")
            relative = file.relative_to(root).as_posix()
            snapshot[relative] = hashlib.sha256(file.read_bytes()).hexdigest()
    return snapshot


def validate_updates(root: Path, old: dict, new: dict) -> None:
    """Compile exact updated bytes before the old server hands off its port."""
    if set(old) - set(new):
        raise HostReloadError("A loaded Studio module was removed; manual review is required.")
    for name, digest in new.items():
        if old.get(name) == digest:
            continue
        path = root / name
        source = path.read_bytes()
        if hashlib.sha256(source).hexdigest() != digest:
            raise HostReloadError("Studio source changed during reload inspection.")
        try:
            compile(source, str(path), "exec")
        except (SyntaxError, UnicodeError, ValueError) as exc:
            raise HostReloadError("Invalid updated Studio Python module: " + name) from exc


def _load_record(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 256 * 1024:
        raise HostReloadError("Unsafe or missing in-progress Studio record.")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise HostReloadError("In-progress Studio record is not an object.")
    return data


def active_work(workspace: Path) -> bool:
    """Fail closed if a queued, executing or uncertain native transfer exists."""
    state = workspace / "autopilot-active.json"
    if state.exists() or state.is_symlink():
        try:
            if _load_record(state).get("status") in IN_PROGRESS_STAGES:
                return True
        except (ValueError, OSError, KeyError, TypeError):
            return True
    jobs = workspace / "jobs"
    if jobs.is_symlink():
        return True
    if not jobs.exists():
        return False
    if not jobs.is_dir():
        return True
    paths = list(jobs.glob("*.json"))
    if len(paths) > 10000:
        return True
    for path in paths:
        try:
            if _load_record(path).get("status") in NATIVE_IN_FLIGHT:
                return True
        except (ValueError, OSError, KeyError, TypeError):
            return True
    return False


class HostCodeWatcher:
    def __init__(self, root: Path, workspace: Path):
        self.root = root.resolve()
        self.workspace = workspace.resolve()
        self.baseline = source_snapshot(self.root)
        self.pending = None
        self.consecutive = 0
        self.state = "CURRENT"
        self.reason = ""
        self._lock = threading.RLock()

    def observe(self, *, busy: bool = False) -> bool:
        """Return True only for stable, valid updates with no active work."""
        with self._lock:
            try:
                changed = source_snapshot(self.root)
                if changed == self.baseline:
                    self.pending, self.consecutive = None, 0
                    self.state, self.reason = "CURRENT", ""
                    return False
                validate_updates(self.root, self.baseline, changed)
                if changed != self.pending:
                    self.pending, self.consecutive = changed, 1
                else:
                    self.consecutive += 1
                if self.consecutive < 2:
                    self.state, self.reason = "VALIDATING_UPDATE", "Verifying a stable repository source revision."
                    return False
                if busy or active_work(self.workspace):
                    self.state, self.reason = "DEFERRED_ACTIVE_TRANSFER", (
                        "A queued, running or partial native transfer is present; it will not be replayed."
                    )
                    return False
                self.state, self.reason = "READY_TO_RELOAD", "Only the Studio localhost server will restart."
                return True
            except (ValueError, OSError, RuntimeError) as exc:
                self.state, self.reason = "BLOCKED_INVALID_CODE", str(exc)[:300]
                self.pending, self.consecutive = None, 0
                return False

    def status(self) -> dict:
        with self._lock:
            return {
                "status": self.state,
                "reason": self.reason,
                "engine_restart_required": False,
                "native_job_replayed": False,
                "server_reloading": self.state == "READY_TO_RELOAD",
            }

    def mutation_safe(self) -> bool:
        """Guard new host mutations after a code edit but before rotation."""
        self.observe(busy=True)
        return self.status()["status"] == "CURRENT"
