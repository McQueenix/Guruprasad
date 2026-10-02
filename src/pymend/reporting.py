"""Rendering results as coloured text, JSON, or unified diffs."""
from __future__ import annotations

import difflib
import json
import os
import sys
from typing import Dict, List, Optional, TextIO

from .models import SEVERITY_ORDER, Issue, SourceMap
from .rules import RULES


class Colors:
    """ANSI colours, switched off when not a terminal or when NO_COLOR is set."""

    def __init__(self, stream: TextIO, disabled: bool = False) -> None:
        isatty = getattr(stream, "isatty", lambda: False)()
        self.enabled = isatty and not disabled and "NO_COLOR" not in os.environ
        if self.enabled and os.name == "nt":
            os.system("")  # enables ANSI escape handling in Windows consoles

    def _wrap(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled else text

    def red(self, text: str) -> str:
        return self._wrap("31", text)

    def yellow(self, text: str) -> str:
        return self._wrap("33", text)

    def cyan(self, text: str) -> str:
        return self._wrap("36", text)

    def green(self, text: str) -> str:
        return self._wrap("32", text)

    def bold(self, text: str) -> str:
        return self._wrap("1", text)

    def dim(self, text: str) -> str:
        return self._wrap("2", text)

    def severity(self, sev: str) -> str:
        label = sev.upper()
        return {"error": self.red, "warning": self.yellow}.get(sev, self.cyan)(label)


def format_issue(issue: Issue, source: Optional[str], colors: Colors) -> str:
    head = (f"{colors.bold(f'{issue.path}:{issue.line}:{issue.col}')} "
            f"{colors.severity(issue.severity)} {colors.bold(issue.code)} {issue.message}")
    if issue.fixable:
        head += " " + colors.green("[auto-fixable]")
    lines = [head]
    if source is not None:
        text = SourceMap(source).line_text(issue.line)
        if text:
            gutter = f"{issue.line:>5} | "
            lines.append(colors.dim(gutter) + text)
            lines.append(" " * len(gutter) + " " * (issue.col - 1) + colors.yellow("^"))
    if issue.hint:
        lines.append(colors.dim(f"   hint: {issue.hint}"))
    return "\n".join(lines)


def format_summary(issues: List[Issue], files: int, colors: Colors) -> str:
    if not issues:
        return colors.green(f"No issues found in {files} file(s).")
    counts: Dict[str, int] = {}
    for issue in issues:
        counts[issue.severity] = counts.get(issue.severity, 0) + 1
    parts = [f"{counts[s]} {s}(s)" for s in sorted(counts, key=lambda s: SEVERITY_ORDER[s])]
    return colors.bold("Summary: ") + ", ".join(parts) + f" across {files} file(s)"


def format_json(issues: List[Issue], errors: List[str], files: int, fixed: int) -> str:
    return json.dumps({
        "files_scanned": files,
        "fixed": fixed,
        "issues": [i.to_dict() for i in issues],
        "errors": errors,
    }, indent=2, ensure_ascii=False)


def _display(path: str) -> str:
    return path.replace("\\", "/").lstrip("/")


def format_diff(path: str, old: str, new: str) -> str:
    diff = difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
                                fromfile=f"a/{_display(path)}", tofile=f"b/{_display(path)}")
    return "".join(diff)


def format_rules() -> str:
    rows = ["CODE  SEVERITY  FIX  TITLE"]
    for rule in RULES.values():
        rows.append(f"{rule.code}  {rule.severity:<8}  {'yes' if rule.fixable else ' - '}  {rule.title}")
    return "\n".join(rows)


def write(text: str, stream: Optional[TextIO] = None) -> None:
    stream = stream or sys.stdout
    try:
        stream.write(text + "\n")
    except UnicodeEncodeError:  # e.g. a legacy Windows console code page
        encoding = getattr(stream, "encoding", None) or "ascii"
        stream.write(text.encode(encoding, "replace").decode(encoding) + "\n")
