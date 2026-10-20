"""Saving and loading the baseline JSON file."""

import json
import os
import tempfile
from dataclasses import dataclass

from .hasher import SUPPORTED_ALGORITHMS, FileRecord

BASELINE_VERSION = 1
DEFAULT_BASELINE_FILE = ".fim_baseline.json"


class BaselineError(Exception):
    pass


@dataclass
class Baseline:
    algorithm: str
    root: str
    recursive: bool
    excludes: list
    created: str
    files: dict  # relative path -> FileRecord


def save_baseline(baseline, path):
    data = {
        "version": BASELINE_VERSION,
        "algorithm": baseline.algorithm,
        "root": baseline.root,
        "recursive": baseline.recursive,
        "excludes": baseline.excludes,
        "created": baseline.created,
        "files": {
            rel: {"hash": rec.hash, "size": rec.size, "mtime": rec.mtime}
            for rel, rec in baseline.files.items()
        },
    }

    # write to a temp file next to the target and rename it into place, so a
    # crash halfway through can't leave a half-written baseline behind.
    # mkstemp creates the file as 0600, so the baseline ends up owner-only.
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".fim_tmp_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp_path, path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def load_baseline(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise BaselineError(f"no baseline found at {path}. Run with --baseline first.")
    except OSError as err:
        raise BaselineError(f"could not read {path}: {err.strerror or err}")
    except ValueError as err:  # bad JSON, or bytes that aren't UTF-8
        raise BaselineError(f"{path} is not a readable baseline file ({err})")

    return _parse(data, path)


def _parse(data, path):
    if not isinstance(data, dict):
        raise BaselineError(f"{path} is not a baseline file")
    if data.get("version") != BASELINE_VERSION:
        raise BaselineError(
            f"{path} has baseline version {data.get('version')!r}, "
            f"this tool reads version {BASELINE_VERSION}"
        )
    if data.get("algorithm") not in SUPPORTED_ALGORITHMS:
        raise BaselineError(f"{path} uses an unknown algorithm: {data.get('algorithm')!r}")

    root = data.get("root")
    recursive = data.get("recursive")
    excludes = data.get("excludes")
    created = data.get("created")
    raw_files = data.get("files")
    if not (
        isinstance(root, str)
        and isinstance(recursive, bool)
        and isinstance(created, str)
        and isinstance(excludes, list)
        and all(isinstance(e, str) for e in excludes)
        and isinstance(raw_files, dict)
    ):
        raise BaselineError(f"{path} is missing settings or has them in the wrong shape")

    files = {}
    for rel, entry in raw_files.items():
        if not (
            isinstance(entry, dict)
            and isinstance(entry.get("hash"), str)
            and isinstance(entry.get("size"), int)
            and isinstance(entry.get("mtime"), (int, float))
        ):
            raise BaselineError(f"{path} has a bad entry for {rel!r}")
        files[rel] = FileRecord(entry["hash"], entry["size"], float(entry["mtime"]))

    return Baseline(data["algorithm"], root, recursive, excludes, created, files)
