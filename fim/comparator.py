"""Compare the saved baseline against what a fresh scan found."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Modified:
    path: str
    old: object  # FileRecord from the baseline
    new: object  # FileRecord from the current scan

    @property
    def size_delta(self):
        return self.new.size - self.old.size


@dataclass
class Diff:
    checked: int = 0
    added: list = field(default_factory=list)
    removed: list = field(default_factory=list)
    modified: list = field(default_factory=list)
    unreadable: dict = field(default_factory=dict)

    @property
    def clean(self):
        # a file we couldn't read is a file we couldn't verify, so it counts
        return not (self.added or self.removed or self.modified or self.unreadable)


def _is_unreadable(path, unreadable):
    # unreadable can hold a directory, which covers everything inside it.
    # "." is what we get if the top directory itself couldn't be listed.
    return any(u == "." or path == u or path.startswith(u + "/") for u in unreadable)


def compare(old_files, new_files, unreadable=None):
    unreadable = unreadable or {}
    diff = Diff(checked=len(new_files), unreadable=dict(unreadable))

    for path in sorted(new_files):
        if path not in old_files:
            diff.added.append(path)
        elif new_files[path].hash != old_files[path].hash:
            diff.modified.append(Modified(path, old_files[path], new_files[path]))

    for path in sorted(old_files):
        if path in new_files:
            continue
        # if we couldn't read it this time, we don't know that it's gone
        if _is_unreadable(path, unreadable):
            continue
        diff.removed.append(path)

    return diff
