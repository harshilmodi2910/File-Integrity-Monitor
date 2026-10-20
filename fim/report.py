"""Turn a Diff into text or JSON."""

import json
from datetime import datetime, timezone


def _short(digest):
    return digest[:16] + "..." if len(digest) > 16 else digest


def _fmt_time(timestamp):
    # UTC so the output reads the same no matter what machine it runs on
    moment = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    return moment.strftime("%Y-%m-%d %H:%M:%S UTC")


def format_text(diff, baseline):
    lines = [
        f"Checked {diff.checked} files against the baseline from "
        f"{baseline.created} ({baseline.algorithm})."
    ]
    if diff.clean:
        lines.append("No changes found.")
        return "\n".join(lines)

    if diff.modified:
        lines += ["", f"MODIFIED ({len(diff.modified)})"]
        for m in diff.modified:
            lines.append(f"  {m.path}")
            lines.append(f"    hash:  {_short(m.old.hash)} -> {_short(m.new.hash)}")
            lines.append(f"    size:  {m.old.size} -> {m.new.size} bytes ({m.size_delta:+d})")
            lines.append(f"    mtime: {_fmt_time(m.old.mtime)} -> {_fmt_time(m.new.mtime)}")

    if diff.added:
        lines += ["", f"ADDED ({len(diff.added)})"]
        lines += [f"  {path}" for path in diff.added]

    if diff.removed:
        lines += ["", f"REMOVED ({len(diff.removed)})"]
        lines += [f"  {path}" for path in diff.removed]

    if diff.unreadable:
        lines += ["", f"UNREADABLE ({len(diff.unreadable)})"]
        lines += [f"  {path}: {msg}" for path, msg in sorted(diff.unreadable.items())]

    lines += [
        "",
        f"Summary: {len(diff.added)} added, {len(diff.removed)} removed, "
        f"{len(diff.modified)} modified, {len(diff.unreadable)} unreadable",
    ]
    return "\n".join(lines)


def format_json(diff, baseline):
    data = {
        "clean": diff.clean,
        "algorithm": baseline.algorithm,
        "baseline_created": baseline.created,
        "checked": diff.checked,
        "added": diff.added,
        "removed": diff.removed,
        "modified": [
            {
                "path": m.path,
                "old_hash": m.old.hash,
                "new_hash": m.new.hash,
                "old_size": m.old.size,
                "new_size": m.new.size,
                "size_delta": m.size_delta,
                "old_mtime": m.old.mtime,
                "new_mtime": m.new.mtime,
            }
            for m in diff.modified
        ],
        "unreadable": [
            {"path": path, "error": msg} for path, msg in sorted(diff.unreadable.items())
        ],
    }
    return json.dumps(data, indent=2)
