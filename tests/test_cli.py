import json
import shutil

from fim.cli import main


def run(argv, capsys):
    code = main([str(a) for a in argv])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_baseline_then_check_on_an_untouched_directory_is_clean(target, baseline_file, capsys):
    code, out, _ = run(["--baseline", target, "--baseline-file", baseline_file], capsys)
    assert code == 0
    assert "4 files hashed with sha256" in out

    code, out, _ = run(["--check", target, "--baseline-file", baseline_file], capsys)
    assert code == 0
    assert "No changes found" in out


def test_baseline_stored_inside_the_target_does_not_flag_itself(target, capsys):
    inside = target / ".fim_baseline.json"
    run(["--baseline", target, "--baseline-file", inside], capsys)

    code, out, _ = run(["--check", target, "--baseline-file", inside], capsys)

    assert code == 0
    assert "No changes found" in out


def test_check_exits_1_and_reports_every_kind_of_change(target, baseline_file, capsys):
    run(["--baseline", target, "--baseline-file", baseline_file], capsys)
    (target / "notes" / "todo.txt").write_text("something else entirely\n")
    (target / "src" / "main.py").unlink()
    (target / "extra.txt").write_text("new")

    code, out, _ = run(["--check", target, "--baseline-file", baseline_file], capsys)

    assert code == 1
    assert "MODIFIED (1)" in out and "notes/todo.txt" in out
    assert "REMOVED (1)" in out and "src/main.py" in out
    assert "ADDED (1)" in out and "extra.txt" in out
    assert "Summary: 1 added, 1 removed, 1 modified, 0 unreadable" in out


def test_baseline_refuses_to_overwrite_without_force(target, baseline_file, capsys):
    run(["--baseline", target, "--baseline-file", baseline_file], capsys)
    first = baseline_file.read_text()
    (target / "extra.txt").write_text("new")

    code, _, err = run(["--baseline", target, "--baseline-file", baseline_file], capsys)
    assert code == 2
    assert "--force" in err
    assert baseline_file.read_text() == first

    code, _, _ = run(["--baseline", target, "--baseline-file", baseline_file, "--force"], capsys)
    assert code == 0
    assert baseline_file.read_text() != first


def test_check_without_a_baseline_exits_2(target, baseline_file, capsys):
    code, _, err = run(["--check", target, "--baseline-file", baseline_file], capsys)
    assert code == 2
    assert "no baseline found" in err


def test_algorithm_comes_from_the_baseline_and_a_mismatch_is_an_error(target, baseline_file, capsys):
    run(["--baseline", target, "--baseline-file", baseline_file, "--algorithm", "sha512"], capsys)

    code, out, _ = run(["--check", target, "--baseline-file", baseline_file], capsys)
    assert code == 0
    assert "sha512" in out

    code, _, err = run(["--check", target, "--baseline-file", baseline_file,
                        "--algorithm", "sha256"], capsys)
    assert code == 2
    assert "sha512" in err


def test_scan_options_are_fixed_when_the_baseline_is_made(target, baseline_file, capsys):
    run(["--baseline", target, "--baseline-file", baseline_file,
         "--no-recursive", "--exclude", "*.md"], capsys)

    code, out, _ = run(["--check", target, "--baseline-file", baseline_file], capsys)
    assert code == 0
    assert "Checked 1 files" in out

    code, _, err = run(["--check", target, "--baseline-file", baseline_file,
                        "--exclude", "*.txt"], capsys)
    assert code == 2
    assert "--exclude" in err


def test_json_report_and_moved_directory_warning(target, baseline_file, tmp_path, capsys):
    run(["--baseline", target, "--baseline-file", baseline_file], capsys)
    moved = tmp_path / "moved"
    shutil.move(str(target), str(moved))
    (moved / "extra.txt").write_text("new")

    code, out, err = run(["--check", moved, "--baseline-file", baseline_file, "--json"], capsys)

    assert code == 1
    report = json.loads(out)
    assert report["clean"] is False
    assert report["added"] == ["extra.txt"]
    assert report["algorithm"] == "sha256"
    assert "the baseline was created for" in err
