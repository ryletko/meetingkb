# Contributing to MeetingKB

Thanks for your interest in contributing! This project is under active
development; expect the structure and docs below to evolve.

## Development setup

Using [uv](https://docs.astral.sh/uv/) (recommended):

```bash
uv venv
uv pip install -e ".[dev]"
```

Or with plain `pip`:

```bash
python -m venv .venv
source .venv/bin/activate  # .venv\Scripts\activate on Windows
pip install -e ".[dev]"
```

Add the `transcribe` extra (`.[transcribe,dev]`) if you also need to run or
test transcription locally.

## Linting

```bash
uv run ruff check .
```

(or `ruff check .` if you're not using `uv`.)

## Running tests

The default test run excludes anything marked `@pytest.mark.integration`
(tests that need OpenSearch, a GPU, `ffmpeg`, or a live LLM endpoint):

```bash
uv run pytest
```

This is enforced by `addopts = "-m 'not integration'"` in `pyproject.toml`,
so a plain `pytest` invocation behaves the same way.

### Running integration tests

Integration tests need real infrastructure present:

```bash
# Start OpenSearch (and make sure ffmpeg is on PATH)
docker compose -f deploy/docker-compose.yml up -d

uv run pytest -m integration
```

Some integration tests additionally require a GPU or a reachable LLM
endpoint (`KB_LLM_BASE_URL` / `KB_LLM_MODEL`); those will skip themselves
gracefully if the dependency isn't available rather than failing the run.

## Pull requests

Please keep changes focused, include tests where practical, and make sure
`ruff check .` and the default (non-integration) test suite pass before
opening a PR.
