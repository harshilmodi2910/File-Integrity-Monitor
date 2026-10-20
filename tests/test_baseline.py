import json

import pytest

from fim.baseline import BASELINE_VERSION, Baseline, BaselineError, load_baseline, save_baseline
from fim.hasher import FileRecord


def make_baseline():
    return Baseline(
        algorithm="sha256",
        root="/some/dir",
        recursive=True,
        excludes=[".git", "*.log"],
        created="2026-01-01T00:00:00+00:00",
        files={"a.txt": FileRecord("abc123", 10, 1700000000.5)},
    )


def test_save_then_load_gives_back_the_same_baseline(tmp_path):
    path = tmp_path / "b.json"
    original = make_baseline()

    save_baseline(original, path)

    assert load_baseline(path) == original
    # no temp files left next to the baseline
    assert [p.name for p in tmp_path.iterdir()] == ["b.json"]


def test_missing_and_unparseable_files_raise_baseline_error(tmp_path):
    with pytest.raises(BaselineError, match="--baseline"):
        load_baseline(tmp_path / "nope.json")

    bad = tmp_path / "bad.json"
    bad.write_text("{ this is not json")
    with pytest.raises(BaselineError, match="not a readable baseline"):
        load_baseline(bad)


def test_wrong_shape_or_version_is_rejected(tmp_path):
    good = {
        "version": BASELINE_VERSION,
        "algorithm": "sha256",
        "root": "/x",
        "recursive": True,
        "excludes": [],
        "created": "2026-01-01T00:00:00+00:00",
        "files": {},
    }
    variants = {
        "list instead of object": [],
        "wrong version": {**good, "version": 99},
        "unknown algorithm": {**good, "algorithm": "md5"},
        "files is a list": {**good, "files": []},
        "entry missing hash": {**good, "files": {"a.txt": {"size": 1, "mtime": 1.0}}},
        "missing root": {k: v for k, v in good.items() if k != "root"},
    }
    for label, data in variants.items():
        path = tmp_path / "variant.json"
        path.write_text(json.dumps(data))
        with pytest.raises(BaselineError):
            load_baseline(path)
