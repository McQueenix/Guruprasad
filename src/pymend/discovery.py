"""Finding Python files, and reading/writing them without changing their encoding."""
from __future__ import annotations

import fnmatch
import io
import os
import tokenize
from typing import Iterable, Iterator, List, Optional, Tuple

DEFAULT_EXCLUDES = [
    ".git", ".hg", ".svn", "__pycache__", ".venv", "venv", "env", ".tox", ".nox",
    "build", "dist", "node_modules", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".eggs", "*.egg-info",
]


def _matches(path: str, patterns: Iterable[str]) -> bool:
    norm = path.replace(os.sep, "/")
    parts = norm.split("/")
    for pattern in patterns:
        pattern = pattern.strip().rstrip("/")
        if not pattern:
            continue
        if fnmatch.fnmatch(norm, pattern) or fnmatch.fnmatch(norm, f"*/{pattern}"):
            return True
        if any(fnmatch.fnmatch(part, pattern) for part in parts):
            return True
    return False


def discover(paths: Iterable[str], exclude: Iterable[str] = ()) -> Iterator[Tuple[str, Optional[str]]]:
    """Yield ``(file_path, error)`` for every Python file under ``paths``.

    Files named explicitly are always included; directories are walked, skipping
    the default excludes plus any user patterns.
    """
    patterns = list(DEFAULT_EXCLUDES) + list(exclude)
    for root in paths:
        if os.path.isfile(root):
            yield root, None
        elif os.path.isdir(root):
            found: List[str] = []
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = sorted(d for d in dirnames if not _matches(os.path.join(dirpath, d), patterns))
                for name in filenames:
                    full = os.path.join(dirpath, name)
                    if name.endswith((".py", ".pyw")) and not _matches(full, patterns):
                        found.append(full)
            for full in sorted(found):
                yield full, None
        else:
            yield root, f"{root}: no such file or directory"


def read_source(path: str) -> Tuple[str, str]:
    """Read a Python file using its declared encoding (PEP 263; BOM aware)."""
    with open(path, "rb") as handle:
        data = handle.read()
    encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
    return data.decode(encoding), encoding


def write_source(path: str, text: str, encoding: str) -> None:
    """Write text back with the same encoding (and BOM) it was read with."""
    with open(path, "wb") as handle:
        handle.write(text.encode(encoding))
