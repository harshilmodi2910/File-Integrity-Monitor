import os

from fim.comparator import compare
from fim.hasher import FileRecord, scan_directory


def snapshot(target):
    return scan_directory(target).files


def test_clean_run_finds_nothing(target):
    before = snapshot(target)
    diff = compare(before, snapshot(target))

    assert diff.clean
    assert diff.added == [] and diff.removed == [] and diff.modified == []
    assert diff.checked == 4


def test_added_file(target):
    before = snapshot(target)
    (target / "notes" / "new.txt").write_text("fresh")

    diff = compare(before, snapshot(target))

    assert diff.added == ["notes/new.txt"]
    assert diff.removed == [] and diff.modified == []
    assert not diff.clean


def test_removed_file(target):
    before = snapshot(target)
    (target / "src" / "main.py").unlink()

    diff = compare(before, snapshot(target))

    assert diff.removed == ["src/main.py"]
    assert diff.added == [] and diff.modified == []


def test_modified_file_carries_old_and_new_details(target):
    before = snapshot(target)
    path = target / "notes" / "todo.txt"
    # write_text would turn \n into \r\n on Windows and throw the byte counts off
    path.write_bytes(b"buy milk\nrenew library card\nreturn the drill\n")

    diff = compare(before, snapshot(target))

    assert [m.path for m in diff.modified] == ["notes/todo.txt"]
    change = diff.modified[0]
    assert change.old.hash != change.new.hash
    assert change.old.size == len(b"buy milk\nrenew library card\n")
    assert change.size_delta == len(b"return the drill\n")
    assert diff.added == [] and diff.removed == []


def test_touching_a_file_without_changing_it_is_not_a_modification(target):
    before = snapshot(target)
    path = target / "readme.txt"
    os.utime(path, (1_000_000_000, 1_000_000_000))

    after = snapshot(target)
    assert after["readme.txt"].mtime != before["readme.txt"].mtime
    assert compare(before, after).clean


def test_rename_shows_up_as_removed_plus_added(target):
    before = snapshot(target)
    (target / "readme.txt").rename(target / "README.txt")

    diff = compare(before, snapshot(target))

    assert diff.removed == ["readme.txt"]
    assert diff.added == ["README.txt"]


def test_unreadable_files_and_directories_are_not_reported_as_removed():
    old = {
        "a.txt": FileRecord("h1", 1, 1.0),
        "locked/b.txt": FileRecord("h2", 1, 1.0),
        "gone.txt": FileRecord("h3", 1, 1.0),
    }
    new = {}
    unreadable = {"a.txt": "Permission denied", "locked": "Permission denied"}

    diff = compare(old, new, unreadable)

    assert diff.removed == ["gone.txt"]
    assert diff.unreadable == unreadable
    assert not diff.clean
