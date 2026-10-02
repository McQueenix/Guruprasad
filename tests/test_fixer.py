"""The fix engine: correct output, unchanged behaviour, and the safety net."""
import ast

from pymend import Edit, analyze_source, apply_edits, fix_source
from pymend import fixer as fixer_module


def fixed(src):
    issues, err = analyze_source(src)
    assert err is None
    return fix_source(src, issues)


def test_fix_mutable_default_inserts_guard():
    result = fixed("def f(x=[]):\n    x.append(1)\n    return x\n")
    assert result.source == (
        "def f(x=None):\n    if x is None:\n        x = []\n    x.append(1)\n    return x\n"
    )


def test_fix_mutable_default_keeps_behaviour():
    result = fixed("def f(x=[]):\n    x.append(1)\n    return x\n")
    namespace = {}
    exec(result.source, namespace)
    first, second = namespace["f"](), namespace["f"]()
    assert first == [1] and second == [1] and first is not second


def test_fix_mutable_default_after_docstring():
    result = fixed('def f(x={}):\n    """Doc."""\n    return x\n')
    assert result.source == (
        'def f(x=None):\n    """Doc."""\n    if x is None:\n        x = {}\n    return x\n'
    )


def test_one_line_function_is_not_fixed():
    result = fixed("def f(x=[]): return x\n")
    assert result.applied == 0


def test_fix_bare_except():
    result = fixed("try:\n    pass\nexcept:\n    pass\n")
    assert "except Exception:" in result.source


def test_fix_none_comparison():
    assert fixed("x = 1\nok = x != None\n").source == "x = 1\nok = x is not None\n"


def test_fix_type_comparison_keeps_exact_type_check():
    assert fixed("x = 1\nok = type(x) == int\n").source == "x = 1\nok = type(x) is int\n"


def test_fix_is_literal():
    assert fixed("x = 1\nok = x is not 'a'\n").source == "x = 1\nok = x != 'a'\n"


def test_fix_unused_import_removes_whole_line():
    assert fixed("import os\nimport sys\nprint(sys)\n").source == "import sys\nprint(sys)\n"


def test_import_sharing_a_line_is_not_removed():
    result = fixed("import os; import sys\nprint(sys)\n")
    assert result.applied == 0


def test_operator_with_comment_between_is_left_alone():
    src = "x = 1\nok = (x ==  # odd but valid\n      None)\n"
    assert fixed(src).applied == 0


def test_non_ascii_before_fix_point():
    src = "s = 'テスト'\nok = 'é' if s == None else 'ü'\n"
    assert fixed(src).source == "s = 'テスト'\nok = 'é' if s is None else 'ü'\n"


def test_crlf_line_endings_are_preserved():
    src = "def f(x=[]):\r\n    return x\r\n\r\ntry:\r\n    pass\r\nexcept:\r\n    pass\r\n"
    out = fixed(src).source
    assert "\n" not in out.replace("\r\n", "")
    assert "    if x is None:\r\n        x = []\r\n" in out
    assert "except Exception:" in out


def test_all_fixes_together_still_parse(buggy_source):
    result = fixed(buggy_source)
    assert result.applied == 6
    ast.parse(result.source)
    remaining = {i.code for i in analyze_source(result.source)[0] if i.fixable}
    assert remaining == set()


def test_fix_is_idempotent():
    once = fixed("import os\ndef f(x=[]):\n    return x == None\n").source
    assert fixed(once).applied == 0


def test_safety_net_discards_broken_result(monkeypatch):
    src = "x = 1\nok = x == None\n"
    monkeypatch.setattr(fixer_module, "apply_edits", lambda source, edits: source + "def (:\n")
    result = fixed(src)
    assert result.source == src
    assert result.applied == 0
    assert "discarded" in result.error


def test_apply_edits_replace_and_insert():
    src = "a = 1\nb = 2\n"
    out = apply_edits(src, [Edit(1, 4, 1, 5, "10"), Edit(2, 0, 2, 0, "# hi\n")])
    assert out == "a = 10\n# hi\nb = 2\n"


def test_overlapping_edits_are_not_both_applied():
    taken = fixer_module._overlaps((0, 5), (3, 8))
    insert_inside = fixer_module._overlaps((4, 4), (0, 8))
    insert_at_edge = fixer_module._overlaps((8, 8), (0, 8))
    assert taken and insert_inside and not insert_at_edge


def test_two_mutable_defaults_in_one_function():
    result = fixed("def f(a=[], b={}):\n    return a, b\n")
    assert result.applied == 2
    namespace = {}
    exec(result.source, namespace)
    assert namespace["f"]() == ([], {})
