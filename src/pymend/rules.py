"""Rule registry: one place that knows every rule code.

Keeping this in one place lets the CLI validate ``--select``/``--ignore`` codes,
print ``--list-rules``, and document the auto-fix capability of each rule.
"""
from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True)
class Rule:
    code: str
    severity: str
    title: str
    fixable: bool


RULES = {
    r.code: r
    for r in [
        Rule("B001", "warning", "mutable default argument", True),
        Rule("B002", "warning", "bare except", True),
        Rule("B003", "warning", "comparison to None/True/False with ==", True),
        Rule("B004", "warning", "type() compared with ==", True),
        Rule("B005", "warning", "imported but unused", True),
        Rule("B006", "error", "assert on a non-empty tuple (always true)", False),
        Rule("B007", "error", "duplicate key in dict literal", False),
        Rule("B008", "warning", "self-assignment (no effect)", False),
        Rule("B009", "warning", "unreachable code after terminal statement", False),
        Rule("B010", "warning", "is/is not comparison with a literal", True),
        Rule("B011", "warning", "comparison of an expression with itself", False),
        Rule("B012", "error", "return/break/continue inside finally", False),
        Rule("B013", "info", "f-string without placeholders", False),
        Rule("B014", "info", "wildcard import", False),
    ]
}

ALL_CODES = frozenset(RULES)
