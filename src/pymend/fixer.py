"""Fix engine: applies span-precise edits, protected by a re-parse safety net."""
from __future__ import annotations

import ast
import dataclasses
import warnings
from typing import Iterable, List, Optional, Sequence, Tuple

from .models import Edit, Issue, SourceMap


@dataclasses.dataclass
class FixResult:
    source: str          # the fixed source (or the original, if nothing changed)
    applied: int         # number of issues fixed
    skipped: int         # fixable issues not applied (overlapping edits / safety net)
    error: Optional[str] = None


def _byte_range(smap: SourceMap, edit: Edit) -> Tuple[int, int]:
    if edit.delete_lines:
        first, last = edit.delete_lines
        return smap.starts[first - 1], smap.line_end(last)
    return smap.offset(edit.line, edit.col), smap.offset(edit.end_line, edit.end_col)


def _overlaps(a: Tuple[int, int], b: Tuple[int, int]) -> bool:
    (s1, e1), (s2, e2) = a, b
    if s1 == e1:  # pure insertion: conflicts only if it lands strictly inside b
        return s2 < s1 < e2
    if s2 == e2:
        return s1 < s2 < e1
    return s1 < e2 and s2 < e1


def apply_edits(source: str, edits: Sequence[Edit]) -> str:
    """Apply edits to ``source``. Edits must not overlap (see ``select_edits``)."""
    smap = SourceMap(source)
    spans = [(*_byte_range(smap, e), e.text.encode("utf-8")) for e in edits]
    data = smap.data
    # Apply from the end of the file backwards so earlier offsets stay valid.
    for start, end, text in sorted(spans, key=lambda s: (s[0], s[1]), reverse=True):
        data = data[:start] + text + data[end:]
    return data.decode("utf-8")


def select_edits(source: str, issues: Iterable[Issue]) -> Tuple[List[Edit], int, int]:
    """Pick the edits of every fixable issue that does not conflict with another.

    An issue's edits are taken all together or not at all.
    Returns ``(edits, applied_issue_count, skipped_issue_count)``.
    """
    smap = SourceMap(source)
    taken: List[Tuple[int, int]] = []
    chosen: List[Edit] = []
    applied = skipped = 0
    for issue in sorted((i for i in issues if i.fixable and i.edits), key=lambda i: (i.line, i.col)):
        ranges = [_byte_range(smap, e) for e in issue.edits]
        if any(_overlaps(r, t) for r in ranges for t in taken):
            skipped += 1
            continue
        taken.extend(ranges)
        chosen.extend(issue.edits)
        applied += 1
    return chosen, applied, skipped


def fix_source(source: str, issues: Iterable[Issue], path: str = "<string>") -> FixResult:
    """Fix every safely fixable issue in ``source``.

    Safety net: the fixed text is parsed again. If it would not compile, *all*
    edits are discarded and the original source is returned untouched.
    """
    edits, applied, skipped = select_edits(source, issues)
    if not edits:
        return FixResult(source, 0, skipped)
    new_source = apply_edits(source, edits)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            ast.parse(new_source, filename=path)
    except (SyntaxError, ValueError) as exc:
        detail = getattr(exc, "msg", str(exc))
        line = getattr(exc, "lineno", "?")
        return FixResult(source, 0, skipped + applied,
                         f"{path}: fixes discarded, result would not parse ({detail} at line {line})")
    return FixResult(new_source, applied, skipped)
