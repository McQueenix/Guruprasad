"""AST-based bug detectors.

Each rule is implemented as a ``visit_*`` method (or a helper called from one)
on :class:`Detector`. A detector records :class:`Issue` objects; when a finding
can be fixed without changing what the program does, it also attaches the
:class:`Edit` spans that perform the fix.
"""
from __future__ import annotations

import ast
import os
import warnings
from typing import List, Optional, Tuple

from .models import Edit, Issue, SourceMap
from .rules import RULES

_MUTABLE_DISPLAYS = (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp)
_MUTABLE_FACTORIES = {"list", "dict", "set", "bytearray"}
_TERMINAL = (ast.Return, ast.Raise, ast.Break, ast.Continue)
_LITERAL_DISPLAYS = (ast.List, ast.Dict, ast.Set, ast.Tuple, ast.ListComp, ast.DictComp, ast.SetComp)
_PURE_EXPRS = (ast.Name, ast.Attribute, ast.Subscript, ast.Constant)
_FUNC_OR_CLASS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
_LOOPS = (ast.For, ast.AsyncFor, ast.While)
_TRY_NODES = tuple(t for t in (getattr(ast, "Try", None), getattr(ast, "TryStar", None)) if t)


def _short(text: str, limit: int = 40) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _is_singleton(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and (node.value is None or isinstance(node.value, bool))


def _is_literal(node: ast.AST) -> bool:
    """True for literals whose identity is not guaranteed (so `is` is a bug)."""
    if isinstance(node, ast.Constant):
        value = node.value
        # bool is a subclass of int, so exclude it explicitly: `x is True` is fine.
        if isinstance(value, bool) or value is None or value is Ellipsis:
            return False
        return isinstance(value, (str, bytes, int, float, complex))
    return isinstance(node, _LITERAL_DISPLAYS)


def _is_type_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "type"
        and len(node.args) == 1
        and not node.keywords
        and not isinstance(node.args[0], ast.Starred)
    )


class Detector(ast.NodeVisitor):
    """Walks an AST and records every issue it can prove."""

    def __init__(self, source: str, path: str) -> None:
        self.source = source
        self.path = path
        self.map = SourceMap(source)
        self.newline = "\r\n" if "\r\n" in source else "\n"
        self.issues: List[Issue] = []
        self._format_specs: set = set()
        self._class_body: set = set()

    # ------------------------------------------------------------------ utils
    def add(self, node: ast.AST, code: str, message: str, hint: str = "",
            edits: Optional[List[Edit]] = None) -> None:
        line, col = node.lineno, node.col_offset  # type: ignore[attr-defined]
        self.issues.append(Issue(
            path=self.path,
            line=line,
            col=self.map.char_col(line, col),
            code=code,
            severity=RULES[code].severity,
            message=message,
            hint=hint,
            fixable=bool(edits),
            edits=list(edits or []),
        ))

    def segment(self, node: ast.AST) -> str:
        return ast.get_source_segment(self.source, node) or ""

    def _operator_edit(self, left: ast.AST, right: ast.AST, expected: Tuple[str, ...],
                       replacement: str) -> Optional[Edit]:
        """Replace the operator text between two operands, if it is exactly one of
        ``expected`` (ignoring whitespace). Returns None when it is anything else
        (comments, parentheses...), so we never guess."""
        between = self.map.slice(left.end_lineno, left.end_col_offset,  # type: ignore[attr-defined]
                                 right.lineno, right.col_offset)  # type: ignore[attr-defined]
        if " ".join(between.split()) not in expected:
            return None
        return Edit(left.end_lineno, left.end_col_offset,  # type: ignore[attr-defined]
                    right.lineno, right.col_offset, f" {replacement} ")  # type: ignore[attr-defined]

    # --------------------------------------------------------------- B001
    def _visit_function(self, node: ast.AST) -> None:
        args = node.args  # type: ignore[attr-defined]
        positional = list(getattr(args, "posonlyargs", [])) + list(args.args)
        pairs = list(zip(positional[len(positional) - len(args.defaults):], args.defaults))
        pairs += [(a, d) for a, d in zip(args.kwonlyargs, args.kw_defaults) if d is not None]
        for arg, default in pairs:
            if self._is_mutable(default):
                text = self.segment(default)
                self.add(
                    default, "B001",
                    f"mutable default argument `{arg.arg}={_short(text)}`",
                    hint="the default is created once and shared by every call; "
                         "use None and build the value inside the function",
                    edits=self._fix_mutable_default(node, arg.arg, default, text),
                )
        self.generic_visit(node)

    visit_FunctionDef = _visit_function
    visit_AsyncFunctionDef = _visit_function

    @staticmethod
    def _is_mutable(node: ast.AST) -> bool:
        if isinstance(node, _MUTABLE_DISPLAYS):
            return True
        return (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in _MUTABLE_FACTORIES)

    def _fix_mutable_default(self, func: ast.AST, name: str, default: ast.AST,
                             text: str) -> Optional[List[Edit]]:
        if default.lineno != default.end_lineno:  # type: ignore[attr-defined]
            return None
        body = func.body  # type: ignore[attr-defined]
        target = body[0]
        if (isinstance(target, ast.Expr) and isinstance(target.value, ast.Constant)
                and isinstance(target.value.value, str)):
            if len(body) == 1:
                return None
            target = body[1]
        # Insert before the target statement (or its first decorator).
        decorators = getattr(target, "decorator_list", [])
        insert_line = min([target.lineno] + [d.lineno for d in decorators])
        if insert_line <= func.lineno:  # type: ignore[attr-defined]  # one-line def
            return None
        line_text = self.map.line_text(insert_line)
        indent = line_text[: len(line_text) - len(line_text.lstrip())]
        if len(indent.encode("utf-8")) != target.col_offset:
            return None
        inner = indent + ("\t" if "\t" in indent else "    ")
        nl = self.newline
        guard = f"{indent}if {name} is None:{nl}{inner}{name} = {text}{nl}"
        return [
            Edit(default.lineno, default.col_offset,  # type: ignore[attr-defined]
                 default.end_lineno, default.end_col_offset, "None"),  # type: ignore[attr-defined]
            Edit(insert_line, 0, insert_line, 0, guard),
        ]

    # --------------------------------------------------------------- B002
    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type is None:
            edits = None
            if self.map.slice(node.lineno, node.col_offset, node.lineno, node.col_offset + 6) == "except":
                edits = [Edit(node.lineno, node.col_offset, node.lineno, node.col_offset + 6,
                              "except Exception")]
            self.add(node, "B002", "bare `except:` clause",
                     hint="it also catches KeyboardInterrupt and SystemExit; "
                          "catch Exception (or something narrower)",
                     edits=edits)
        self.generic_visit(node)

    # ------------------------------------------- B003 / B004 / B010 / B011
    def visit_Compare(self, node: ast.Compare) -> None:
        operands = [node.left] + list(node.comparators)
        single = len(node.ops) == 1
        for i, op in enumerate(node.ops):
            left, right = operands[i], operands[i + 1]
            self._check_singleton(node, left, op, right, single)
            self._check_type_compare(node, left, op, right, single)
            self._check_is_literal(node, left, op, right, single)
            self._check_self_compare(node, left, op, right)
        self.generic_visit(node)

    def _check_singleton(self, node, left, op, right, single) -> None:
        if not isinstance(op, (ast.Eq, ast.NotEq)):
            return
        const = right if _is_singleton(right) else left if _is_singleton(left) else None
        if const is None:
            return
        value = const.value
        is_eq = isinstance(op, ast.Eq)
        edits = None
        if value is None:
            if single:
                op_text, new = ("==", "is") if is_eq else ("!=", "is not")
                edit = self._operator_edit(left, right, (op_text,), new)
                edits = [edit] if edit else None
            self.add(node, "B003", f"comparison to None should use `{'is' if is_eq else 'is not'}`",
                     hint="`==` can be overridden by __eq__; `is None` is exact and faster",
                     edits=edits)
        else:
            # Not auto-fixed: `x == True` and `x is True` behave differently for 1, "yes", etc.
            self.add(node, "B003", f"comparison to {value!r} with `{'==' if is_eq else '!='}`",
                     hint=f"use `if x:` / `if not x:` (or `is {value!r}` if you really need the singleton); "
                          "not auto-fixed because it could change behaviour")

    def _check_type_compare(self, node, left, op, right, single) -> None:
        if not isinstance(op, (ast.Eq, ast.NotEq)):
            return
        if not (_is_type_call(left) or _is_type_call(right)):
            return
        is_eq = isinstance(op, ast.Eq)
        edits = None
        if single:
            # `type(x) is T` keeps the exact same behaviour; isinstance() would not
            # (it also accepts subclasses), so we suggest it but never apply it.
            op_text, new = ("==", "is") if is_eq else ("!=", "is not")
            edit = self._operator_edit(left, right, (op_text,), new)
            edits = [edit] if edit else None
        self.add(node, "B004", f"`type()` compared with `{'==' if is_eq else '!='}`",
                 hint="use `isinstance(x, T)` to accept subclasses; the auto-fix uses "
                      "`type(x) is T`, which keeps the exact same behaviour",
                 edits=edits)

    def _check_is_literal(self, node, left, op, right, single) -> None:
        if not isinstance(op, (ast.Is, ast.IsNot)):
            return
        if not (_is_literal(right) or _is_literal(left)):
            return
        is_is = isinstance(op, ast.Is)
        edits = None
        if single:
            op_text, new = ("is", "==") if is_is else ("is not", "!=")
            edit = self._operator_edit(left, right, (op_text,), new)
            edits = [edit] if edit else None
        self.add(node, "B010", f"`{'is' if is_is else 'is not'}` used with a literal",
                 hint="identity of literals is not guaranteed; compare values with "
                      f"`{'==' if is_is else '!='}`",
                 edits=edits)

    def _check_self_compare(self, node, left, op, right) -> None:
        if not isinstance(left, _PURE_EXPRS) or not isinstance(right, _PURE_EXPRS):
            return
        if ast.dump(left) != ast.dump(right):
            return
        self.add(node, "B011", f"`{_short(self.segment(left))}` is compared with itself",
                 hint="this is always the same result; if it is a NaN check, use math.isnan()")

    # --------------------------------------------------------------- B006
    def visit_Assert(self, node: ast.Assert) -> None:
        if isinstance(node.test, ast.Tuple) and node.test.elts:
            self.add(node, "B006", "assert on a non-empty tuple is always true",
                     hint="write `assert cond, \"message\"` without the parentheses")
        self.generic_visit(node)

    # --------------------------------------------------------------- B007
    def visit_Dict(self, node: ast.Dict) -> None:
        constants: dict = {}
        names: set = set()
        for key in node.keys:
            if key is None:  # **unpacking
                continue
            if isinstance(key, ast.Constant):
                try:
                    duplicate = key.value in constants
                except TypeError:
                    continue
                if duplicate:
                    self._report_duplicate_key(key)
                else:
                    constants[key.value] = key
            elif isinstance(key, ast.Name):
                if key.id in names:
                    self._report_duplicate_key(key)
                names.add(key.id)
        self.generic_visit(node)

    def _report_duplicate_key(self, key: ast.AST) -> None:
        self.add(key, "B007", f"duplicate key `{_short(self.segment(key))}` in dict literal",
                 hint="the earlier value is silently overwritten; decide which one you meant")

    # --------------------------------------------------------------- B008
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        # `x = x` directly in a class body copies a name into the class; that's legitimate.
        self._class_body.update(id(stmt) for stmt in node.body)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        if (len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Name)
                and node.targets[0].id == node.value.id
                and id(node) not in self._class_body):
            self.add(node, "B008", f"self-assignment `{node.value.id} = {node.value.id}` has no effect",
                     hint="remove it, or check whether you meant a different variable")
        self.generic_visit(node)

    # --------------------------------------------------------------- B012
    def _visit_try(self, node: ast.AST) -> None:
        for stmt in getattr(node, "finalbody", []):
            self._scan_finally(stmt, in_loop=False)
        self.generic_visit(node)

    visit_Try = _visit_try
    visit_TryStar = _visit_try

    def _scan_finally(self, stmt: ast.AST, in_loop: bool) -> None:
        if isinstance(stmt, _FUNC_OR_CLASS):
            return
        if isinstance(stmt, ast.Return) or (isinstance(stmt, (ast.Break, ast.Continue)) and not in_loop):
            word = type(stmt).__name__.lower()
            self.add(stmt, "B012", f"`{word}` inside `finally` swallows any active exception",
                     hint="move it out of the finally block; Python 3.14 warns about this too")
            return
        for field in ("body", "orelse", "finalbody", "handlers"):
            children = getattr(stmt, field, None)
            if not isinstance(children, list):
                continue
            child_in_loop = in_loop or (field == "body" and isinstance(stmt, _LOOPS))
            for child in children:
                if isinstance(child, ast.ExceptHandler):
                    for inner in child.body:
                        self._scan_finally(inner, child_in_loop)
                else:
                    self._scan_finally(child, child_in_loop)
        for case in getattr(stmt, "cases", []) or []:  # match statements
            for inner in case.body:
                self._scan_finally(inner, in_loop)

    # --------------------------------------------------------------- B013
    def visit_FormattedValue(self, node: ast.FormattedValue) -> None:
        if node.format_spec is not None:
            # f"{x:>10}" stores ">10" as a nested JoinedStr; that is not a bug.
            self._format_specs.add(id(node.format_spec))
        self.generic_visit(node)

    def visit_JoinedStr(self, node: ast.JoinedStr) -> None:
        if id(node) not in self._format_specs and not any(
                isinstance(v, ast.FormattedValue) for v in node.values):
            self.add(node, "B013", "f-string has no placeholders",
                     hint="remove the `f` prefix, or add the missing {...}")
        self.generic_visit(node)

    # --------------------------------------------------------------- B014
    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if any(alias.name == "*" for alias in node.names):
            self.add(node, "B014", f"wildcard import `from {'.' * node.level}{node.module or ''} import *`",
                     hint="import the names you need; star imports hide where names come from")
        self.generic_visit(node)

    # --------------------------------------------------------------- B009
    def check_unreachable(self, tree: ast.AST) -> None:
        for node in ast.walk(tree):
            for field in ("body", "orelse", "finalbody"):
                stmts = getattr(node, field, None)
                if not isinstance(stmts, list):
                    continue
                for current, following in zip(stmts, stmts[1:]):
                    if isinstance(current, _TERMINAL):
                        word = type(current).__name__.lower()
                        self.add(following, "B009", f"unreachable code after `{word}`",
                                 hint="this statement can never run; remove it or fix the control flow")
                        break

    # --------------------------------------------------------------- B005
    def check_unused_imports(self, tree: ast.Module) -> None:
        if os.path.basename(self.path) == "__init__.py":
            return  # package __init__ files usually re-export names on purpose
        used = self._used_names(tree)
        top_level = {id(stmt) for stmt in tree.body}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                bound = [(a, a.asname or a.name.split(".")[0]) for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.module == "__future__" or any(a.name == "*" for a in node.names):
                    continue
                bound = [(a, a.asname or a.name) for a in node.names]
            else:
                continue
            unused = [
                name for alias, name in bound
                if name not in used and not (alias.asname and alias.asname == alias.name)
            ]
            if not unused:
                continue
            edits = None
            if len(unused) == len(bound) and id(node) in top_level and self._owns_lines(node):
                edits = [Edit(node.lineno, 0, node.end_lineno, 0,  # type: ignore[attr-defined]
                              delete_lines=(node.lineno, node.end_lineno))]  # type: ignore[attr-defined]
            names = ", ".join(f"`{n}`" for n in unused)
            hint = "remove it" if edits else (
                "remove the unused name(s); only whole top-level import statements are auto-fixed")
            self.add(node, "B005", f"{names} imported but unused", hint=hint, edits=edits)

    def _owns_lines(self, node: ast.AST) -> bool:
        """True when nothing but this statement (and maybe a comment) is on its lines."""
        first = self.map.line_text(node.lineno)  # type: ignore[attr-defined]
        if first[: node.col_offset].strip():  # type: ignore[attr-defined]
            return False
        last_raw = self.map.data[self.map.starts[node.end_lineno - 1]:  # type: ignore[attr-defined]
                                 self.map.line_end(node.end_lineno)]  # type: ignore[attr-defined]
        rest = last_raw[node.end_col_offset:].decode("utf-8", "replace").strip()  # type: ignore[attr-defined]
        return rest == "" or rest.startswith("#")

    @staticmethod
    def _used_names(tree: ast.AST) -> set:
        used = set()
        annotations = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                used.add(node.id)
            elif isinstance(node, ast.arg) and node.annotation is not None:
                annotations.append(node.annotation)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns is not None:
                annotations.append(node.returns)
            elif isinstance(node, ast.AnnAssign):
                annotations.append(node.annotation)
            # Names listed in __all__ count as used (explicit re-exports).
            if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets):
                    value = node.value
                    if isinstance(value, (ast.List, ast.Tuple)):
                        for elt in value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                used.add(elt.value)
        # String annotations such as  def f(x: "Path")  also use names.
        for ann in annotations:
            for sub in ast.walk(ann):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    try:
                        parsed = ast.parse(sub.value, mode="eval")
                    except SyntaxError:
                        continue
                    used.update(n.id for n in ast.walk(parsed) if isinstance(n, ast.Name))
        return used


def analyze_source(source: str, path: str = "<string>") -> Tuple[List[Issue], Optional[str]]:
    """Analyse Python source text.

    Returns ``(issues, error)``. ``error`` is a message when the source could not
    be parsed (in which case ``issues`` is empty).
    """
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # e.g. SyntaxWarning for `x is 1`
            tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return [], f"{path}:{exc.lineno}:{exc.offset}: syntax error: {exc.msg}"
    except ValueError as exc:  # e.g. source contains null bytes
        return [], f"{path}: cannot parse: {exc}"

    detector = Detector(source, path)
    detector.visit(tree)
    detector.check_unreachable(tree)
    detector.check_unused_imports(tree)
    issues = sorted(detector.issues, key=lambda i: (i.line, i.col, i.code))
    return issues, None
