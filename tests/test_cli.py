"""End-to-end behaviour of the command-line interface."""
import json

from pymend.cli import main


def test_report_only_does_not_modify(buggy_file, capsys):
    before = buggy_file.read_text(encoding="utf-8")
    assert main([str(buggy_file), "--no-color"]) == 0
    assert buggy_file.read_text(encoding="utf-8") == before
    assert "B001" in capsys.readouterr().out


def test_check_exits_1_when_issues(buggy_file):
    assert main([str(buggy_file), "--check", "--no-color"]) == 1


def test_check_exits_0_when_clean(tmp_path):
    clean = tmp_path / "clean.py"
    clean.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    assert main([str(clean), "--check"]) == 0


def test_fix_writes_file(buggy_file, capsys):
    main([str(buggy_file), "--fix", "--no-color"])
    text = buggy_file.read_text(encoding="utf-8")
    assert "except Exception:" in text and "cache=None" in text
    assert "Fixed 6 issue(s)." in capsys.readouterr().out


def test_diff_previews_without_writing(buggy_file, capsys):
    before = buggy_file.read_text(encoding="utf-8")
    main([str(buggy_file), "--fix", "--diff", "--no-color"])
    assert buggy_file.read_text(encoding="utf-8") == before
    out = capsys.readouterr().out
    assert "+    if cache is None:" in out and "would be applied" in out


def test_json_output(buggy_file, capsys):
    main([str(buggy_file), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["files_scanned"] == 1
    assert {"path", "line", "col", "code", "severity", "message", "fixable"} <= set(data["issues"][0])


def test_select_and_ignore(buggy_file, capsys):
    main([str(buggy_file), "--json", "--select", "B001,B002", "--ignore", "B002"])
    found = {i["code"] for i in json.loads(capsys.readouterr().out)["issues"]}
    assert found == {"B001"}


def test_unknown_rule_code_is_an_error(buggy_file):
    assert main([str(buggy_file), "--select", "B999"]) == 2


def test_syntax_error_exits_2(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("def (:\n", encoding="utf-8")
    assert main([str(bad)]) == 2


def test_missing_path_exits_2(tmp_path):
    assert main([str(tmp_path / "nope.py")]) == 2


def test_directory_walk_and_exclude(tmp_path, capsys):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("import os\n", encoding="utf-8")
    (tmp_path / "migrations").mkdir()
    (tmp_path / "migrations" / "m.py").write_text("import os\n", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "v.py").write_text("import os\n", encoding="utf-8")
    main([str(tmp_path), "--json", "--exclude", "migrations"])
    data = json.loads(capsys.readouterr().out)
    assert data["files_scanned"] == 1
    assert data["issues"][0]["path"].endswith("a.py")


def test_list_rules(capsys):
    assert main(["--list-rules"]) == 0
    out = capsys.readouterr().out
    assert all(f"B{n:03d}" in out for n in range(1, 15))


def test_no_paths_is_an_error():
    assert main([]) == 2


def test_fix_preserves_utf8_bom(tmp_path):
    path = tmp_path / "bom.py"
    path.write_bytes(b"\xef\xbb\xbfimport os\nx = 1\n")
    main([str(path), "--fix"])
    assert path.read_bytes() == b"\xef\xbb\xbfx = 1\n"
