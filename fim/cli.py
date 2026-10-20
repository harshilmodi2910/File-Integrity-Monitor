"""Command line entry point.

Exit codes: 0 clean (or baseline written), 1 changes found or files that
couldn't be read, 2 the tool itself couldn't do what you asked.
"""

import argparse
import os
import sys
from datetime import datetime, timezone

from .baseline import DEFAULT_BASELINE_FILE, Baseline, BaselineError, load_baseline, save_baseline
from .comparator import compare
from .hasher import DEFAULT_ALGORITHM, DEFAULT_EXCLUDES, SUPPORTED_ALGORITHMS, scan_directory
from .report import format_json, format_text


class CliError(Exception):
    pass


def build_parser():
    parser = argparse.ArgumentParser(
        prog="fim",
        description="Hash the files in a directory, then check later for added, "
                    "removed or modified files.",
        allow_abbrev=False,
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--baseline", action="store_true",
                      help="hash the directory and save the result as the baseline")
    mode.add_argument("--check", action="store_true",
                      help="compare the directory against the saved baseline")

    parser.add_argument("directory", help="directory to scan")
    parser.add_argument("--baseline-file", default=DEFAULT_BASELINE_FILE, metavar="PATH",
                        help=f"where the baseline lives (default: {DEFAULT_BASELINE_FILE} "
                             "in the current directory)")
    parser.add_argument("--algorithm", choices=SUPPORTED_ALGORITHMS, default=None,
                        help=f"hash algorithm for --baseline (default: {DEFAULT_ALGORITHM}). "
                             "--check always uses the one stored in the baseline")
    parser.add_argument("--exclude", action="append", default=[], metavar="PATTERN",
                        help="glob pattern to skip, can be repeated. "
                             f"{', '.join(DEFAULT_EXCLUDES)} are always skipped. "
                             "Only used with --baseline")
    parser.add_argument("--no-recursive", action="store_true",
                        help="only scan the top level of the directory. Only used with --baseline")
    parser.add_argument("--force", action="store_true",
                        help="let --baseline overwrite an existing baseline file")
    parser.add_argument("--json", action="store_true",
                        help="print the --check report as JSON")
    return parser


def _require_directory(path):
    if not os.path.isdir(path):
        raise CliError(f"{path} is not a directory")
    return path


def run_baseline(args):
    root = _require_directory(args.directory)
    if os.path.exists(args.baseline_file) and not args.force:
        raise CliError(f"{args.baseline_file} already exists. Use --force to overwrite it.")

    algorithm = args.algorithm or DEFAULT_ALGORITHM
    recursive = not args.no_recursive
    excludes = list(dict.fromkeys(list(DEFAULT_EXCLUDES) + args.exclude))

    result = scan_directory(root, algorithm, recursive, excludes,
                            skip_paths=[args.baseline_file])
    baseline = Baseline(
        algorithm=algorithm,
        root=os.path.realpath(root),
        recursive=recursive,
        excludes=excludes,
        created=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        files=result.files,
    )
    save_baseline(baseline, args.baseline_file)

    print(f"Baseline written to {args.baseline_file}: "
          f"{len(result.files)} files hashed with {algorithm}.")
    for rel, msg in sorted(result.unreadable.items()):
        print(f"warning: could not read {rel}: {msg}", file=sys.stderr)
    return 0


def run_check(args):
    root = _require_directory(args.directory)
    if args.exclude or args.no_recursive:
        raise CliError("--exclude and --no-recursive are set when the baseline is "
                       "created. Make a new baseline to change them.")

    baseline = load_baseline(args.baseline_file)
    if args.algorithm and args.algorithm != baseline.algorithm:
        raise CliError(f"the baseline was made with {baseline.algorithm} but "
                       f"--algorithm {args.algorithm} was given. Hashes from different "
                       "algorithms can't be compared.")
    if os.path.realpath(root) != baseline.root:
        print(f"warning: the baseline was created for {baseline.root}, "
              f"but you are checking {os.path.realpath(root)}", file=sys.stderr)

    result = scan_directory(root, baseline.algorithm, baseline.recursive,
                            baseline.excludes, skip_paths=[args.baseline_file])
    diff = compare(baseline.files, result.files, result.unreadable)

    formatter = format_json if args.json else format_text
    print(formatter(diff, baseline))
    return 0 if diff.clean else 1


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return run_baseline(args) if args.baseline else run_check(args)
    except (CliError, BaselineError) as err:
        print(f"fim: error: {err}", file=sys.stderr)
        return 2
    except OSError as err:
        print(f"fim: error: {err}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
