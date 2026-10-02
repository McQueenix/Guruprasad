.PHONY: install test lint build clean

install:
	pip install -e ".[dev]"

test:
	python -m pytest -q

lint:
	pymend src/ tests/ --check --exclude tests/data

build:
	python -m build

clean:
	rm -rf build dist src/*.egg-info .pytest_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
