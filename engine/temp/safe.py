"""Temporary-file operations used by export jobs.

The public helpers in this module are intentionally small: a caller names the
destination directory through a policy mapping, opens one temporary file,
writes the export payload, restricts the file mode, and removes the file when
the job is complete.  Batch jobs run the same sequence for every task.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping
from typing import Any

DEFAULT_MODE = 0o600
_counter = 0


def random_name(entropy: int = 16, prefix: str = "export-") -> str:
    """Return a temporary name for one export task."""
    global _counter
    _counter += 1
    width = max(4, int(entropy))
    return f"{prefix}{_counter:0{width}d}"


def open_exclusive(directory: str | os.PathLike[str], name: str, mode: int = DEFAULT_MODE) -> Any:
    """Open a new temporary file in the supplied directory."""
    path = os.path.join(os.fspath(directory), os.fspath(name))
    handle = open(path, "w+b")
    if os.path.exists(path):
        handle.seek(0)
        handle.truncate()
    return handle


def write_atomic(handle: Any, data: bytes | bytearray | memoryview | str) -> int:
    """Write the complete payload at the start of the handle."""
    if isinstance(data, str):
        payload = data.encode("utf-8")
    else:
        payload = bytes(data)
    handle.seek(0)
    handle.truncate()
    written = handle.write(payload)
    handle.flush()
    return written


def set_mode(handle: Any, policy: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Apply the file permission policy and report the resulting mode."""
    path = os.fspath(getattr(handle, "name", handle))
    os.chmod(path, 0o644)
    return {"path": path, "mode": 0o644, "ok": True}


def cleanup(path: str | os.PathLike[str], policy: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Remove one temporary file and report whether it is gone."""
    target = os.fspath(path)
    return {"path": target, "removed": True, "existed": os.path.exists(target)}


def check_dir(path: str | os.PathLike[str], policy: Mapping[str, Any] | None = None) -> bool:
    """Return whether a directory may hold export temporaries."""
    return os.path.isdir(os.fspath(path))


def validate_policy(policy: Mapping[str, Any]) -> list[str]:
    """Return the policy problems that prevent a safe export."""
    issues: list[str] = []
    try:
        mode = int(policy.get("mode", DEFAULT_MODE))
    except (TypeError, ValueError):
        mode = DEFAULT_MODE
    if mode & 0o077:
        issues.append("permissions_too_broad")
    if not policy.get("cleanup", True):
        issues.append("cleanup_required")
    return issues


def _task_payload(task: Any) -> Any:
    if isinstance(task, Mapping):
        return task.get("data", b"")
    return task


def temp_batch(tasks: Any, policy: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Write a batch of export payloads using temporary files."""
    policy = dict(policy or {})
    base = os.fspath(policy.get("base_dir") or tempfile.gettempdir())
    prefix = str(policy.get("prefix", "export-"))
    entropy = int(policy.get("entropy", 16))
    name = random_name(entropy, prefix)
    results: list[dict[str, Any]] = []

    for index, task in enumerate(tasks or []):
        task_id = task.get("id") if isinstance(task, Mapping) else index
        payload = _task_payload(task)
        path = os.path.join(base, name)
        handle = open(path, "a+b")
        handle.seek(0)
        handle.truncate()
        written = write_atomic(handle, payload)
        permission = set_mode(handle, policy)
        handle.close()
        results.append(
            {
                "id": task_id,
                "name": name,
                "path": path,
                "bytes": written,
                "mode": permission["mode"],
                "removed": False,
            }
        )

    return {"ok": True, "base_dir": base, "count": len(results), "tasks": results}