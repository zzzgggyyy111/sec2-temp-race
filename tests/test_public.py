from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from engine.temp import safe


def _policy(base: Path, **overrides: object) -> dict[str, object]:
    policy: dict[str, object] = {
        "base_dir": str(base),
        "prefix": "public-",
        "entropy": 16,
        "mode": 0o600,
        "exclusive": True,
        "cleanup": True,
    }
    policy.update(overrides)
    return policy


def test_random_name_is_unpredictable() -> None:
    names = [safe.random_name(16, "public-") for _ in range(8)]
    suffixes = [name.removeprefix("public-") for name in names]

    assert len(set(names)) == len(names)
    assert all(not suffix.isdigit() for suffix in suffixes)
    assert all(len(suffix) >= 24 for suffix in suffixes)


def test_open_exclusive_refuses_an_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "claimed.bin"
    target.write_bytes(b"owner-data")

    with pytest.raises(FileExistsError):
        handle = safe.open_exclusive(tmp_path, target.name, 0o600)
        handle.close()

    assert target.read_bytes() == b"owner-data"


def test_permissions_are_owner_only(tmp_path: Path) -> None:
    target = tmp_path / "permission.bin"
    handle = target.open("w+b")
    try:
        info = safe.set_mode(handle, {"mode": 0o600})
    finally:
        handle.close()

    assert info["mode"] == 0o600
    if os.name != "nt":
        assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_cleanup_deletes_the_temporary_file(tmp_path: Path) -> None:
    target = tmp_path / "cleanup.bin"
    target.write_bytes(b"payload")

    info = safe.cleanup(target, {})

    assert info["removed"] is True
    assert not target.exists()


def test_batch_tasks_use_independent_temporary_files(tmp_path: Path) -> None:
    tasks = [
        {"id": "first", "data": b"alpha"},
        {"id": "second", "data": b"beta"},
    ]

    result = safe.temp_batch(tasks, _policy(tmp_path))

    assert result["ok"] is True
    assert result["count"] == 2
    paths = [task["path"] for task in result["tasks"]]
    assert len(set(paths)) == 2
    assert all(task["removed"] is True for task in result["tasks"])
    assert not any(Path(path).exists() for path in paths)