"""Command-line interface: argument parsing and orchestration."""
from __future__ import annotations

import argparse
import os
import sys
from typing import Dict, List, Optional, Sequence

from . import __version__
from .config import load_config
from .detectors import analyze_source
from .discovery import discover, read_source, write_source
from .fixer import fix_source
from .models import Issue
from .reporting import (Colors, format_diff, format_issue, format_json, format_rules,
                        format_summary, write)
from .rules import ALL_CODES

EXIT_OK, EXIT_ISSUES, EXIT_ERROR = 0, 1, 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pymend",
        description="Offline Python bug finder and safe auto-fixer (standard library only).",
    )
    parser.add_argument("paths", nargs="*", help="files or directories to check")
    parser.add_argument("--fix", action="store_true", help="apply safe auto-fixes in place")
    parser.add_argument("--diff", action="store_true",
                        help="show the fixes as a unified diff instead of writing files")
    parser.add_argument("--check", action="store_true",
                        help="exit with code 1 if any issue remains (for CI)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--select", help="comma-separated rule codes to run (default: all)")
    parser.add_argument("--ignore", help="comma-separated rule codes to skip")
    parser.add_argument("--exclude", help="comma-separated paths/globs to skip")
    parser.add_argument("--config", help="path to a pyproject.toml or pymend.ini")
    parser.add_argument("--list-rules", action="store_true", help="show every rule and exit")
    parser.add_argument("--no-color", action="store_true", help="disable coloured output")
    parser.add_argument("--version", action="version", version=f"pymend {__version__}")
    return parser


def _codes(value: Optional[str]) -> List[str]:
    return [c.strip().upper() for c in (value or "").split(",") if c.strip()]


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    out = sys.stdout
    colors = Colors(out, disabled=args.no_color or args.json)

    if args.list_rules:
        write(format_rules(), out)
        return EXIT_OK
    if not args.paths:
        parser.print_usage(sys.stderr)
        write("pymend: error: give at least one file or directory (or --list-rules)", sys.stderr)
        return EXIT_ERROR

    config = load_config(args.config, os.getcwd())
    select = _codes(args.select) or config.select
    ignore = set(config.ignore) | set(_codes(args.ignore))
    unknown = sorted((set(select) | ignore) - ALL_CODES)
    if unknown:
        write(f"pymend: error: unknown rule code(s): {', '.join(unknown)} (see --list-rules)", sys.stderr)
        return EXIT_ERROR
    active = (set(select) if select else set(ALL_CODES)) - ignore
    exclude = config.exclude + [p.strip() for p in (args.exclude or "").split(",") if p.strip()]

    errors: List[str] = []
    all_issues: List[Issue] = []
    sources: Dict[str, str] = {}
    diffs: List[str] = []
    files = fixed = 0
    preview = args.diff
    for path, problem in discover(args.paths, exclude):
        if problem:
            errors.append(problem)
            continue
        files += 1
        try:
            source, encoding = read_source(path)
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            errors.append(f"{path}: cannot read: {exc}")
            continue
        issues, error = analyze_source(source, path)
        if error:
            errors.append(error)
            continue
        issues = [i for i in issues if i.code in active]

        if (args.fix or preview) and any(i.fixable for i in issues):
            result = fix_source(source, issues, path)
            if result.error:
                errors.append(result.error)
            elif result.applied:
                fixed += result.applied
                if preview:
                    diffs.append(format_diff(path, source, result.source))
                else:
                    write_source(path, result.source, encoding)
                    source = result.source
                    issues = [i for i in analyze_source(source, path)[0] if i.code in active]
        sources[path] = source
        all_issues.extend(issues)

    if args.json:
        write(format_json(all_issues, errors, files, fixed), out)
    else:
        for diff in diffs:
            write(diff.rstrip("\n"), out)
        if not preview:
            for issue in all_issues:
                write(format_issue(issue, sources.get(issue.path), colors), out)
                write("", out)
        for error in errors:
            write(colors.red(f"error: {error}"), sys.stderr)
        if preview:
            write(f"{fixed} fix(es) would be applied. Run with --fix (without --diff) to write them.", out)
        else:
            if args.fix:
                write(colors.green(f"Fixed {fixed} issue(s)."), out)
            write(format_summary(all_issues, files, colors), out)
            fixable = sum(1 for i in all_issues if i.fixable)
            if fixable and not args.fix:
                write(f"Run with --fix to apply {fixable} safe auto-fix(es) "
                      "(the result is re-parsed before anything is written).", out)

    if errors:
        return EXIT_ERROR
    if args.check and all_issues:
        return EXIT_ISSUES
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
