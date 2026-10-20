import hashlib
import os
from types import SimpleNamespace

import pytest

from fim import hasher
from fim.hasher import (
    DEFAULT_EXCLUDES,
    SUPPORTED_ALGORITHMS,
    FileChangedError,
    hash_file,
    scan_directory,
)


def test_known_digest_and_every_algorithm_matches_hashlib(tmp_path):
    f = tmp_path / "abc.txt"
    f.write_bytes(b"abc")

    # the standard SHA-256 test vector for "abc"
    expected = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert hash_file(f).hash == expected

    for algorithm in SUPPORTED_ALGORITHMS:
        assert hash_file(f, algorithm).hash == hashlib.new(algorithm, b"abc").hexdigest()


def test_small_chunk_size_gives_same_digest(tmp_path):
    f = tmp_path / "data.bin"
    data = bytes(range(256)) * 10
    f.write_bytes(data)

    record = hash_file(f, chunk_size=7)

    assert record.hash == hashlib.sha256(data).hexdigest()
    assert record.size == len(data)


def test_unsupported_algorithm_is_rejected(tmp_path):
    f = tmp_path / "a.txt"
    f.write_bytes(b"x")
    with pytest.raises(ValueError):
        hash_file(f, "md5")


def test_file_changed_during_read_raises(tmp_path, monkeypatch):
    f = tmp_path / "busy.txt"
    f.write_bytes(b"some data")

    real_fstat = os.fstat
    calls = []

    def fake_fstat(fd):
        real = real_fstat(fd)
        calls.append(fd)
        if len(calls) == 2:  # the check after reading looks like the file grew
            return SimpleNamespace(st_size=real.st_size + 1,
                                   st_mtime_ns=real.st_mtime_ns,
                                   st_mtime=real.st_mtime)
        return real

    monkeypatch.setattr(hasher.os, "fstat", fake_fstat)

    with pytest.raises(FileChangedError):
        hash_file(f)


def test_scan_recursive_and_non_recursive(target):
    full = scan_directory(target)
    assert sorted(full.files) == ["notes/ideas.md", "notes/todo.txt", "readme.txt", "src/main.py"]

    top_only = scan_directory(target, recursive=False)
    assert sorted(top_only.files) == ["readme.txt"]


def test_scan_excludes(target):
    (target / ".git").mkdir()
    (target / ".git" / "config").write_text("x")
    (target / "src" / "__pycache__").mkdir()
    (target / "src" / "__pycache__" / "main.pyc").write_bytes(b"x")
    (target / "debug.log").write_text("x")
    (target / "notes" / "scratch.log").write_text("x")

    default_only = scan_directory(target, excludes=DEFAULT_EXCLUDES)
    assert ".git/config" not in default_only.files
    assert "src/__pycache__/main.pyc" not in default_only.files
    assert "debug.log" in default_only.files

    with_logs = scan_directory(target, excludes=list(DEFAULT_EXCLUDES) + ["*.log"])
    assert "debug.log" not in with_logs.files
    assert "notes/scratch.log" not in with_logs.files

    with_path = scan_directory(target, excludes=["notes/*"])
    assert "notes/todo.txt" not in with_path.files
    assert "readme.txt" in with_path.files


def test_scan_skips_symlinks_and_the_baseline_file(target):
    baseline_inside = target / "baseline.json"
    baseline_inside.write_text("{}")
    try:
        os.symlink(target / "readme.txt", target / "link_to_file")
        os.symlink(target / "notes", target / "link_to_dir")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not available here")

    result = scan_directory(target, skip_paths=[baseline_inside])

    assert "link_to_file" not in result.files
    assert not any(path.startswith("link_to_dir") for path in result.files)
    assert "baseline.json" not in result.files
    assert "readme.txt" in result.files


def test_scan_reports_unreadable_files_and_directories(target, monkeypatch):
    real_hash_file = hasher.hash_file

    def picky_hash_file(path, *args, **kwargs):
        if str(path).endswith("todo.txt"):
            raise PermissionError(13, "Permission denied")
        return real_hash_file(path, *args, **kwargs)

    # chmod can't be used for this because it does nothing when tests run as root
    with monkeypatch.context() as m:
        m.setattr(hasher, "hash_file", picky_hash_file)
        result = scan_directory(target)
    assert result.unreadable == {"notes/todo.txt": "Permission denied"}
    assert "notes/ideas.md" in result.files
    assert "notes/todo.txt" not in result.files

    real_walk = os.walk

    def walk_with_error(top, **kwargs):
        kwargs["onerror"](PermissionError(13, "Permission denied", os.path.join(top, "locked")))
        yield from real_walk(top, **kwargs)

    with monkeypatch.context() as m:
        m.setattr(hasher.os, "walk", walk_with_error)
        result = scan_directory(target)
    assert result.unreadable == {"locked": "Permission denied"}
    assert "readme.txt" in result.files
