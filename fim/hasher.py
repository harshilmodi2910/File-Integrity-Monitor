"""Hashing a single file, and walking a directory to hash everything in it."""

import fnmatch
import hashlib
import os
import stat
from dataclasses import dataclass, field

SUPPORTED_ALGORITHMS = ("sha256", "sha512", "sha1", "blake2b")
DEFAULT_ALGORITHM = "sha256"
DEFAULT_EXCLUDES = (".git", "__pycache__")
CHUNK_SIZE = 1024 * 1024


class FileChangedError(OSError):
    """The file's size or mtime moved while we were reading it."""


@dataclass(frozen=True)
class FileRecord:
    hash: str
    size: int
    mtime: float


@dataclass
class ScanResult:
    files: dict = field(default_factory=dict)       # relative path -> FileRecord
    unreadable: dict = field(default_factory=dict)  # relative path -> error message


def hash_file(path, algorithm=DEFAULT_ALGORITHM, chunk_size=CHUNK_SIZE):
    if algorithm not in SUPPORTED_ALGORITHMS:
        raise ValueError(f"unsupported algorithm: {algorithm}")

    digest = hashlib.new(algorithm)
    with open(path, "rb") as f:
        # fstat on the open handle so size and mtime describe the file we read,
        # not whatever is at that path a moment later
        before = os.fstat(f.fileno())
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
        after = os.fstat(f.fileno())

    # This only catches a write that changed the size or mtime while we were
    # reading. A write that leaves both the same would get through.
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise FileChangedError(f"file changed while it was being read: {path}")

    return FileRecord(digest.hexdigest(), after.st_size, after.st_mtime)


def is_excluded(rel_path, patterns):
    # A pattern can match the last part of the path (".git", "*.log") or the
    # whole relative path ("docs/drafts/*"). fnmatch's * also matches "/".
    name = rel_path.rsplit("/", 1)[-1]
    for pattern in patterns:
        if fnmatch.fnmatchcase(name, pattern) or fnmatch.fnmatchcase(rel_path, pattern):
            return True
    return False


def scan_directory(root, algorithm=DEFAULT_ALGORITHM, recursive=True,
                   excludes=DEFAULT_EXCLUDES, skip_paths=()):
    """Hash every regular file under root.

    Symlinks, sockets, fifos and device files are skipped. A file or directory
    we can't read goes into `unreadable` instead of stopping the whole scan.
    skip_paths is for files that should never be hashed, like the baseline.
    """
    root = os.path.realpath(root)
    skip = {os.path.realpath(p) for p in skip_paths}
    result = ScanResult()

    def on_walk_error(err):
        # os.walk drops directories it can't list unless we ask to hear about it
        rel = os.path.relpath(err.filename, root).replace(os.sep, "/")
        result.unreadable[rel] = err.strerror or str(err)

    for dirpath, dirnames, filenames in os.walk(root, onerror=on_walk_error):
        rel_dir = os.path.relpath(dirpath, root)
        rel_dir = "" if rel_dir == "." else rel_dir.replace(os.sep, "/")

        kept = []
        for name in sorted(dirnames):
            rel = f"{rel_dir}/{name}" if rel_dir else name
            full = os.path.join(dirpath, name)
            if os.path.islink(full) or is_excluded(rel, excludes):
                continue
            kept.append(name)
        # editing dirnames in place is how os.walk lets you prune the walk
        dirnames[:] = kept if recursive else []

        for name in sorted(filenames):
            rel = f"{rel_dir}/{name}" if rel_dir else name
            full = os.path.join(dirpath, name)
            if full in skip or is_excluded(rel, excludes):
                continue
            try:
                # lstat so a symlink shows up as a symlink. Opening a fifo
                # would hang, which is why only regular files get through.
                if not stat.S_ISREG(os.lstat(full).st_mode):
                    continue
                result.files[rel] = hash_file(full, algorithm)
            except OSError as err:
                result.unreadable[rel] = err.strerror or str(err)

    return result
