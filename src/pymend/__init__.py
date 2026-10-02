"""pymend - offline Python bug finder and safe auto-fixer (standard library only)."""
from __future__ import annotations

from .detectors import analyze_source
from .fixer import FixResult, apply_edits, fix_source
from .models import Edit, Issue
from .rules import RULES, Rule

__version__ = "1.0.0"

__all__ = [
    "Edit",
    "FixResult",
    "Issue",
    "RULES",
    "Rule",
    "analyze_source",
    "apply_edits",
    "fix_source",
    "__version__",
]
