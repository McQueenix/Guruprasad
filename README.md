# pymend

**Offline Python bug finder and safe auto-fixer — standard library only.**

pymend reads Python code *without running it*, finds 14 common bug patterns, and
can safely fix 6 of them by itself. It has **zero dependencies**, makes no network
or AI calls, and runs anywhere Python 3.8+ is installed — including locked-down
machines where you can't `pip install` much.

```text
$ pymend src/
src/api.py:7:23 WARNING B001 mutable default argument `cache={}` [auto-fixable]
    7 | def lookup(key, cache={}):
                              ^
   hint: the default is created once and shared by every call; use None and build the value inside the function

Summary: 1 warning(s) across 12 file(s)
Run with --fix to apply 1 safe auto-fix(es) (the result is re-parsed before anything is written).
```

## How it works

1. **Read** – each file is parsed into an abstract syntax tree with Python's built-in `ast` module.
2. **Check** – a single tree walk runs all 14 rules.
3. **Fix safely** – each fix is an exact edit at the node's position (not a regex).
   Fixes that would overlap are skipped, and the whole file is parsed again
   afterwards. If the result would not compile, **all** edits are thrown away
   and the file is left untouched.

Fixes are only applied when they **cannot change what the program does**.
Anything that needs a human decision (which duplicate dict key did you mean?)
is reported, never rewritten.

## Rules

| Code | Severity | What it catches | Auto-fix |
|------|----------|-----------------|----------|
| B001 | warning | Mutable default argument `def f(x=[])` | `x=None` + `if x is None:` guard |
| B002 | warning | Bare `except:` | `except Exception:` |
| B003 | warning | `== None` / `== True` / `== False` | `is None` / `is not None` (True/False reported only) |
| B004 | warning | `type(x) == T` | `type(x) is T` (same behaviour; consider `isinstance`) |
| B005 | warning | Imported but never used | removes whole top-level import lines |
| B006 | error | `assert (cond, "msg")` — always true | – |
| B007 | error | Duplicate key in a dict literal | – |
| B008 | warning | Self-assignment `x = x` | – |
| B009 | warning | Unreachable code after `return`/`raise`/`break`/`continue` | – |
| B010 | warning | `is` / `is not` with a literal (`x is 1`) | `==` / `!=` |
| B011 | warning | Comparing an expression with itself (`a == a`) | – |
| B012 | error | `return`/`break`/`continue` inside `finally` | – |
| B013 | info | f-string with no `{...}` placeholder | – |
| B014 | info | Wildcard `import *` | – |

**Why `== True` is not auto-fixed:** `x == True` and `x is True` give different
answers when `x` is `1` or `"yes"`, so changing it automatically could break code.

## Install

```bash
git clone https://github.com/YOUR-USERNAME/pymend.git
cd pymend
pip install .            # or: pip install -e ".[dev]" for development
```

This gives you the `pymend` command (and `python -m pymend`).

## Usage

```bash
pymend path [path ...]            # report only
pymend src/ --fix                 # apply safe auto-fixes in place
pymend src/ --diff                # preview the fixes as a unified diff (writes nothing)
pymend src/ --check               # exit 1 if any issue remains (CI gate)
pymend src/ --json                # machine-readable output
pymend src/ --select B001,B005    # only these rules
pymend src/ --ignore B013         # everything except these
pymend src/ --exclude "migrations,*_pb2.py"
pymend --list-rules
```

**Exit codes:** `0` OK · `1` issues found (with `--check`) · `2` syntax error,
unreadable or missing file, or bad arguments.

## Configuration

Optional. Command-line flags are combined with the config file.

`pyproject.toml` (read on Python 3.11+):

```toml
[tool.pymend]
ignore = ["B013"]
exclude = ["migrations", "*_pb2.py"]
```

or `pymend.ini` (works on every supported Python):

```ini
[pymend]
ignore = B013
exclude = migrations, *_pb2.py
```

## CI integration

GitHub Actions:

```yaml
- run: pip install .
- run: pymend src/ --check
```

pre-commit (`.pre-commit-config.yaml` in your project):

```yaml
repos:
  - repo: https://github.com/YOUR-USERNAME/pymend
    rev: v1.0.0
    hooks:
      - id: pymend
```

## Project layout

```text
src/pymend/
  models.py      Issue / Edit dataclasses and the byte-position SourceMap
  rules.py       rule registry (codes, severity, fixability)
  detectors.py   the AST analyser (analyze_source)
  fixer.py       edit engine + re-parse safety net (fix_source)
  reporting.py   text / JSON / diff output
  discovery.py   file walking, excludes, encoding-preserving read/write
  config.py      pyproject.toml / pymend.ini loading
  cli.py         argument parsing and orchestration
tests/           pytest suite (detectors, fixer, CLI, config)
```

## Development

```bash
pip install -e ".[dev]"
python -m pytest -q                              # run the tests
pymend src/ tests/ --check --exclude tests/data  # pymend checks its own code
python -m build                                  # build wheel + sdist
```

### Adding a rule

Add an entry to `rules.py`, write a `visit_<Node>` method (or helper) on
`Detector` in `detectors.py` that calls `self.add(...)`, and — only if the fix
cannot change behaviour — attach `Edit` objects. The shared fix engine and the
safety net handle the rest. Add a test for both the bad and the good case.

## About

pymend was built with AI-assisted development (Claude).

## License

MIT — see [LICENSE](LICENSE).
