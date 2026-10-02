"""Configuration loading from pymend.ini and pyproject.toml."""
import json
import sys

import pytest

from pymend.cli import main
from pymend.config import load_config


def test_ini_config(tmp_path):
    (tmp_path / "pymend.ini").write_text(
        "[pymend]\nignore = b013, B014\nexclude = migrations, *_pb2.py\n", encoding="utf-8")
    cfg = load_config(start_dir=str(tmp_path))
    assert cfg.ignore == ["B013", "B014"]
    assert cfg.exclude == ["migrations", "*_pb2.py"]


@pytest.mark.skipif(sys.version_info < (3, 11), reason="tomllib needs Python 3.11+")
def test_pyproject_config(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pymend]\nselect = ["B001"]\nexclude = ["build"]\n', encoding="utf-8")
    cfg = load_config(start_dir=str(tmp_path))
    assert cfg.select == ["B001"] and cfg.exclude == ["build"]


def test_no_config_gives_defaults(tmp_path):
    cfg = load_config(start_dir=str(tmp_path))
    assert cfg.select == [] and cfg.ignore == [] and cfg.exclude == []


def test_cli_uses_config_from_cwd(tmp_path, monkeypatch, capsys):
    (tmp_path / "pymend.ini").write_text("[pymend]\nignore = B005\n", encoding="utf-8")
    (tmp_path / "a.py").write_text("import os\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    main(["a.py", "--json"])
    assert json.loads(capsys.readouterr().out)["issues"] == []
