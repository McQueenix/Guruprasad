import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))  # run tests without installing

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


@pytest.fixture
def buggy_source():
    with open(os.path.join(DATA, "buggy_sample.py"), encoding="utf-8") as handle:
        return handle.read()


@pytest.fixture
def buggy_file(tmp_path, buggy_source):
    path = tmp_path / "buggy.py"
    path.write_text(buggy_source, encoding="utf-8")
    return path
