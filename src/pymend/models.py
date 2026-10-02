"""Core data models shared across the analyzer."""
from __future__ import annotations

import dataclasses
import re
from typing import List, Optional, Tuple

# Lower number = higher priority when sorting / summarising.
SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}

# Python's tokenizer treats \r\n, \r and \n as line breaks.
_NEWLINE_RE = re.compile(rb"\r\n|\r|\n")


@dataclasses.dataclass
class Edit:
    """A single text replacement.

    Positions follow the AST convention: ``line`` is 1-based and ``col`` is a
    0-based *UTF-8 byte* offset into that line. When ``delete_lines`` is set to
    ``(first, last)`` (inclusive, 1-based) those whole lines are removed instead.
    """

    line: int
    col: int
    end_line: int
    end_col: int
    text: str = ""
    delete_lines: Optional[Tuple[int, int]] = None


@dataclasses.dataclass
class Issue:
    """One finding reported by a detector."""

    path: str
    line: int
    col: int  # 1-based character column, for display
    code: str
    severity: str
    message: str
    hint: str = ""
    fixable: bool = False
    edits: List[Edit] = dataclasses.field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "line": self.line,
            "col": self.col,
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "hint": self.hint,
            "fixable": self.fixable,
        }


class SourceMap:
    """Maps AST (line, byte-column) positions onto the UTF-8 encoded source."""

    def __init__(self, source: str) -> None:
        self.data = source.encode("utf-8")
        self.starts = [0]
        for match in _NEWLINE_RE.finditer(self.data):
            self.starts.append(match.end())

    def offset(self, line: int, col: int) -> int:
        return self.starts[line - 1] + col

    def line_end(self, line: int) -> int:
        """Byte offset just past the line, including its line break."""
        return self.starts[line] if line < len(self.starts) else len(self.data)

    def slice(self, line: int, col: int, end_line: int, end_col: int) -> str:
        start, end = self.offset(line, col), self.offset(end_line, end_col)
        return self.data[start:end].decode("utf-8", "replace")

    def line_text(self, line: int) -> str:
        if line < 1 or line > len(self.starts):
            return ""
        raw = self.data[self.starts[line - 1]:self.line_end(line)]
        return raw.decode("utf-8", "replace").rstrip("\r\n")

    def char_col(self, line: int, col: int) -> int:
        """Convert a 0-based byte column into a 1-based character column."""
        start = self.starts[line - 1] if line <= len(self.starts) else len(self.data)
        return len(self.data[start:start + col].decode("utf-8", "replace")) + 1
