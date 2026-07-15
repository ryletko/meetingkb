# Contributing to MeetingKB

Thanks for your interest in contributing! This project is under active
development; expect the structure and docs below to evolve.

## Development setup

```bash
uv venv
uv pip install -e ".[dev]"
```

## Running tests

```bash
uv run pytest tests/
```

## Linting

```bash
uv run ruff check .
```

## Pull requests

Please keep changes focused, include tests where practical, and make sure
`ruff check .` and the test suite pass before opening a PR.
