"""Every rule fires on bad code, and stays quiet on good code."""
import pytest

from pymend import analyze_source


def codes(src, path="<test>"):
    issues, err = analyze_source(src, path)
    assert err is None, err
    return [i.code for i in issues]


@pytest.mark.parametrize(
    "src, expected",
    [
        ("def f(x=[]):\n    return x\n", "B001"),
        ("try:\n    pass\nexcept:\n    pass\n", "B002"),
        ("x = 1\nif x == None:\n    pass\n", "B003"),
        ("x = 1\nok = type(x) == int\n", "B004"),
        ("import os\n", "B005"),
        ("x = 1\nassert (x, 'msg')\n", "B006"),
        ("d = {'a': 1, 'a': 2}\n", "B007"),
        ("x = 1\nx = x\n", "B008"),
        ("def f():\n    return 1\n    print('dead')\n", "B009"),
        ("x = 1\nok = x is 1\n", "B010"),
        ("x = 1\nok = x == x\n", "B011"),
        ("def f():\n    try:\n        pass\n    finally:\n        return 1\n", "B012"),
        ("x = f'no placeholder'\n", "B013"),
        ("from os import *\n", "B014"),
    ],
)
def test_each_rule_fires(src, expected):
    assert expected in codes(src)


def test_buggy_sample_full_coverage(buggy_source):
    found = set(codes(buggy_source))
    assert {f"B{n:03d}" for n in range(1, 15)} <= found


def test_clean_code_has_no_issues():
    src = (
        "def add(a, b):\n"
        "    return a + b\n\n"
        "def safe(x=None):\n"
        "    if x is None:\n"
        "        x = []\n"
        "    return x\n"
    )
    assert codes(src) == []


def test_is_with_bool_or_none_is_fine():
    assert codes("x = 1\na = x is True\nb = x is None\nc = x is not False\n") == []


def test_is_with_int_one_is_flagged():
    # Regression: 1 == True in Python, so a naive "not in (True, False)" check missed this.
    assert "B010" in codes("x = 1\nok = x is 1\n")


def test_comparison_to_true_is_reported_but_not_fixable():
    issues, _ = analyze_source("x = 1\nok = x == True\n")
    b003 = [i for i in issues if i.code == "B003"]
    assert len(b003) == 1 and b003[0].fixable is False


def test_future_import_not_flagged():
    assert "B005" not in codes("from __future__ import annotations\n\nx = 1\nprint(x)\n")


def test_dunder_all_counts_as_use():
    assert "B005" not in codes("import os\n\n__all__ = ['os']\n")


def test_explicit_reexport_alias_not_flagged():
    assert "B005" not in codes("import os as os\n")


def test_init_file_imports_not_flagged():
    assert "B005" not in codes("import os\n", path="pkg/__init__.py")


def test_string_annotation_counts_as_use():
    src = "from pathlib import Path\n\ndef f(p: 'Path') -> None:\n    return None\n"
    assert "B005" not in codes(src)


def test_partial_unused_import_reported_but_not_fixable():
    issues, _ = analyze_source("from os import path, getcwd\nprint(path)\n")
    b005 = [i for i in issues if i.code == "B005"]
    assert len(b005) == 1
    assert "getcwd" in b005[0].message
    assert b005[0].fixable is False


def test_nested_import_not_fixable():
    src = "def f():\n    import json\n    return 1\n"
    issues, _ = analyze_source(src)
    assert [i.fixable for i in issues if i.code == "B005"] == [False]


def test_format_spec_is_not_an_empty_fstring():
    assert "B013" not in codes("x = 3.14159\ns = f'{x:>10.2f}'\n")


def test_class_body_self_assignment_allowed():
    assert "B008" not in codes("x = 1\nclass C:\n    x = x\n")


def test_break_in_loop_inside_finally_allowed():
    src = (
        "try:\n    pass\nfinally:\n"
        "    for i in range(3):\n        if i:\n            break\n"
    )
    assert "B012" not in codes(src)


def test_break_directly_in_finally_flagged():
    src = "for i in range(3):\n    try:\n        pass\n    finally:\n        break\n"
    assert "B012" in codes(src)


def test_duplicate_numeric_keys_follow_python_equality():
    # 1 and True are the same dict key in Python.
    assert "B007" in codes("d = {1: 'a', True: 'b'}\n")


def test_duplicate_name_keys():
    assert "B007" in codes("k = 1\nd = {k: 1, k: 2}\n")


def test_self_compare_ignores_function_calls():
    assert "B011" not in codes("import random\nok = random.random() == random.random()\n")


def test_mutable_factory_call_default():
    assert "B001" in codes("def f(x=list()):\n    return x\n")


def test_keyword_only_mutable_default():
    assert "B001" in codes("def f(*, x={}):\n    return x\n")


def test_syntax_error_is_reported():
    issues, err = analyze_source("def (:\n", "<test>")
    assert issues == []
    assert err is not None and "syntax error" in err


def test_columns_are_character_based_with_non_ascii():
    issues, _ = analyze_source("s = 'テスト'; ok = s == None\n")
    b003 = [i for i in issues if i.code == "B003"][0]
    assert b003.col == len("s = 'テスト'; ok = ") + 1
