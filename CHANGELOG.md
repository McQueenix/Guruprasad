# Changelog

## 1.0.0 — 2026-10-02

- 14 AST-based rules (B001–B014); 6 of them can be auto-fixed.
- Safe fixing: span-precise edits, conflicting edits skipped, and the whole file
  is re-parsed after fixing — if it would not compile, nothing is written.
- Fixes never change program behaviour: `== None` → `is None`,
  `type(x) == T` → `type(x) is T`; `== True/False` is reported but not auto-fixed.
- Handles UTF-8 (including non-ASCII text before a fix), BOMs, PEP 263 encodings
  and CRLF line endings.
- CLI: `--fix`, `--diff`, `--check`, `--json`, `--select`, `--ignore`,
  `--exclude`, `--config`, `--list-rules`, `--no-color`, `--version`.
- Configuration via `pyproject.toml` (`[tool.pymend]`) or `pymend.ini`.
- GitHub Actions CI and a pre-commit hook.
