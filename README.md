# file-integrity-monitor

A command-line tool that hashes every file in a directory, saves the result as a baseline, and on a later run tells you which files were added, removed or modified since then. Python 3.9 or newer, standard library only (pytest is just for the tests).

It's a portfolio project, so think of it as a small version of what AIDE or Tripwire do, not a replacement for them. The limitations section below is long on purpose.

## Usage

There's no install step. Clone the repo and run it from the repo root:

```
python -m fim --baseline path/to/dir
python -m fim --check path/to/dir
```

The first command hashes everything under the directory and writes `.fim_baseline.json` to your current working directory. The second hashes the directory again and compares it to that file.

Here's a run on a small folder, with a few changes made between the baseline and the second check:

```
$ python -m fim --baseline project
Baseline written to .fim_baseline.json: 3 files hashed with sha256.

$ python -m fim --check project
Checked 3 files against the baseline from 2026-10-14T20:12:55+00:00 (sha256).

MODIFIED (1)
  docs/notes.txt
    hash:  123de939f995d0d5... -> 563520bd29cfa342...
    size:  10 -> 24 bytes (+14)
    mtime: 2026-10-14 20:12:48 UTC -> 2026-10-14 20:12:56 UTC

ADDED (1)
  todo.txt

REMOVED (1)
  old.txt

Summary: 1 added, 1 removed, 1 modified, 0 unreadable
```

The text report cuts hashes to 16 characters to keep lines short. `--json` prints the full ones.

### Options

| Flag | What it does |
| --- | --- |
| `--baseline` | Hash the directory and save the baseline. Refuses to overwrite an existing baseline unless you also pass `--force`. |
| `--check` | Compare the directory to the saved baseline. |
| `--baseline-file PATH` | Where the baseline is stored. Default is `.fim_baseline.json` in the current directory. |
| `--algorithm NAME` | `sha256` (default), `sha512`, `sha1` or `blake2b`. Only used with `--baseline`. `--check` uses whatever the baseline recorded and exits with an error if you pass a different one. |
| `--exclude PATTERN` | Glob pattern to skip, can be given more than once. Only used with `--baseline`. |
| `--no-recursive` | Only scan the top level of the directory. Only used with `--baseline`. |
| `--force` | Let `--baseline` overwrite an existing baseline file. |
| `--json` | Print the `--check` report as JSON. |

The algorithm, the exclude list and the recursive setting are stored in the baseline, and `--check` reads them back from there. If I let `--check` take its own excludes, a mismatch would show up as a pile of added or removed files that aren't real changes. So passing `--exclude` or `--no-recursive` to `--check` is an error. To change them, make a new baseline.

### Exit codes

- `0`: nothing changed, or the baseline was written
- `1`: files were added, removed or modified, or some files couldn't be read
- `2`: the tool couldn't do what you asked (not a directory, no baseline or a broken one, baseline already exists, bad flags)

Because of the exit code you can use it in a script or a cron job, for example `python -m fim --check /srv/site || notify-me`.

## What gets scanned

- Recursive by default.
- `.git` and `__pycache__` are always skipped. Extra patterns from `--exclude` are matched against the last part of a path (`*.log`, `node_modules`) or against the whole relative path (`docs/drafts/*`). Matching is case sensitive, and a `*` also matches `/`. There's no flag to turn the default excludes off, you'd have to edit `DEFAULT_EXCLUDES` in `fim/hasher.py`.
- Symlinks, sockets, fifos and device files are skipped. I skip symlinks because following them can loop or lead outside the directory you meant to watch.
- If the baseline file sits inside the scanned directory, it's skipped by its exact path so it doesn't flag itself.
- A file or folder that can't be read doesn't stop the run. It's listed under UNREADABLE and the exit code is 1, since a file I couldn't read is a file I couldn't verify. During `--baseline` it only prints a warning, and that file will show up as added on a later check once it becomes readable.
- A file counts as modified only if its hash changed. Touching a file without changing its contents isn't reported, and the old and new mtimes are only shown as extra detail.

The baseline is plain JSON: the settings above, plus a hash, size and mtime for each relative path. You can open it in an editor. On Linux the file ends up readable by the owner only, because of how I write it (see `save_baseline`). I don't know what that does for permissions on Windows.

## A design decision I went back and forth on

The default location of the baseline file took me longer than I expected.

My first idea was to put it inside the directory being monitored, so it travels with the folder and nobody has to pass a path. Then I ran two checks in a row and the baseline reported itself as modified, since it was now one of the files being hashed and it changes every time it's written. Excluding it by name looked fine for a while, until I thought about a legitimate file called `.fim_baseline.json` somewhere deeper in the tree that should be monitored.

So I swung the other way and thought about a fixed folder in the home directory. That fixes the self-hashing problem, but two different projects would then share one baseline unless I invented a naming scheme, and I didn't want to build that for a small tool.

What I ended up with is `.fim_baseline.json` in the current working directory, `--baseline-file` to put it somewhere else, and a check that skips the baseline by its resolved path, so only that one exact file is ignored wherever it lives. The default depends on where you happen to run the command, which isn't great, and I'm still not sure it beats the home directory option.

## Choosing an algorithm

SHA-256 is the default. In February 2017, researchers at Google and CWI Amsterdam published two different PDF files with the same SHA-1 hash, the first practical SHA-1 collision.

That attack needs the attacker to craft both versions of the file, which isn't quite what a file integrity monitor has to defend against, and as far as I know nobody can make a new file that matches an existing SHA-1 hash. I kept `sha1` in the list anyway for comparing against older checksum lists, but I wouldn't pick it for new baselines.

## Limitations

- **Race between hashing and reading (TOCTOU).** The directory is listed first and the files are hashed afterwards, so a file can change, get replaced or vanish in between. While hashing a file I compare its size and mtime from before and after the read, and if they moved the file is reported as unreadable with a "changed while it was being read" message. That catches a write that happens during the read. It misses a write that keeps the same size and mtime, and it does nothing for the gap between the listing and opening the file. A file deleted in that gap shows up as unreadable on that run instead of removed.
- **Permissions and ownership aren't checked.** Only file contents are hashed, so a `chmod` or `chown` goes unnoticed, and so do changes to extended attributes. Adding it would mean storing mode, uid and gid in the baseline and comparing them. I haven't done that, so it's open.
- **The baseline isn't protected.** It's plain JSON with no signature. Anyone who can change the monitored files and also write the baseline can change both and nothing will complain. If that matters, keep the baseline somewhere the monitored account can't write to, or on read-only media.
- **Renames look like a removal plus an addition.** There's no rename detection.
- **Only files are tracked.** An empty directory being added or removed isn't noticed.
- **Everything is rehashed on every run.** I don't use size or mtime to skip files that look unchanged, because that would defeat part of the point. I haven't measured how slow it gets on large directories.
- **No way to accept a single change.** After an expected change you rebuild the whole baseline with `--baseline --force`.
- **One-shot only.** There's no watch mode. A cron job calling `--check` is the closest thing.
- **Tested on Linux and Windows, not macOS.** I ran the tests on Linux and on Windows. On Windows the symlink test skips itself because creating symlinks needs extra privileges there, so symlink handling is only tested on Linux. My first Windows run also failed one test: it wrote a file with `write_text`, and Windows turns `\n` into `\r\n`, which changed the byte count the test expected. The tool was fine, the test was wrong.

## Tests

```
pip install -r requirements.txt
pytest
```

There are 26 tests. They cover added, removed and modified files and a clean run, plus excludes, non-recursive scans, symlinks, unreadable files, a file changing mid-read, a corrupted baseline, an algorithm mismatch, and the CLI exit codes. The tests copy `tests/sample_dir` into a temp folder before touching anything, so the committed sample never changes.

The unreadable-file tests fake the permission error instead of using `chmod`, because `chmod` does nothing when the tests run as root.

## License

MIT, see `LICENSE`.
