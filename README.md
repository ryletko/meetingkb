# MeetingKB

MeetingKB is a local knowledge base for meeting recordings: it transcribes
your audio/video (Whisper), indexes the transcripts (SQLite + OpenSearch),
lets you search across them with transliteration/typo/fuzzy matching, browse
meetings in a video player with seek-bar hover-preview thumbnails, and ask
questions about what was discussed via a local or OpenAI-compatible LLM.
Everything runs on your own machine — no data leaves your infrastructure
unless you point the LLM at a remote endpoint yourself.

## Features

- **Transcription** — batch-transcribes media files with `faster-whisper`
  (CPU or CUDA GPU), skipping files that already have a transcript.
- **Indexing** — parses Whisper JSON transcripts into SQLite (always) and
  OpenSearch (optional), with per-meeting term detection from a
  user-supplied glossary.
- **Search** — transliteration-aware (Cyrillic ↔ Latin), typo-tolerant
  (Levenshtein-based fuzzy matching), and Russian-suffix-stemming query
  expansion, with inline match highlighting.
- **Browse** — a Streamlit UI with a video player (seek-bar hover-preview
  thumbnails generated from the source video) and a Range-capable local
  media server.
- **Ask** — retrieval-augmented question answering over your transcripts via
  any OpenAI-compatible chat endpoint (local, e.g. Ollama/vLLM, or hosted).
- **Cross-platform CLI** (`kb`) that replaces ad hoc shell scripts with a
  single Typer entrypoint, plus `kb doctor` to check your environment.

## Architecture

MeetingKB is organized as a small set of layers:

```
domain/config    meetingkb.models, meetingkb.config.Settings
                       │
services         meetingkb.ingest   (transcriber, indexer, thumbnails)
                 meetingkb.search   (storage/SQLite, opensearch_backend, query)
                 meetingkb.rag      (LLM client, context assembly)
                       │
interfaces       meetingkb.web (Streamlit UI + media server)
                 meetingkb.cli (Typer commands)
```

- **Domain/config** — `Settings` (pydantic-settings), loaded via
  `get_settings()` from environment variables / a `.env` file, is the single
  source of truth for paths, endpoints, and tuning knobs. `meetingkb.models`
  holds the domain dataclasses used along the way (e.g. `RagDocument`, the
  model threaded through the RAG path from search hit to prompt context).
- **Services** — ingest (transcribe media, build the index, generate
  thumbnails), search (SQLite storage, OpenSearch backend, fuzzy/transliteration
  query expansion), and RAG (an OpenAI-compatible chat client plus context
  assembly from search results) are independent of each other and of any
  particular interface.
- **Interfaces** — `web/app.py` (the Streamlit UI) and `cli.py` (the `kb`
  Typer CLI) are thin: each calls `get_settings()` and constructs the
  services it needs directly (`OpenSearchClient`, `storage.connect`,
  `OpenAICompatibleClient`, `FasterWhisperTranscriber`, etc.).
  `meetingkb.context.AppContext` is a small optional convenience that wires
  those same services together behind a single object for programmatic
  embedding; it is not imported by the shipped CLI or UI and is currently
  exercised only by the test suite.

## Requirements

- Python ≥ 3.11
- [Docker](https://www.docker.com/) — to run OpenSearch (optional if you use
  `--no-opensearch` / SQLite-only search)
- [`ffmpeg`](https://ffmpeg.org/) on `PATH` — used for thumbnail generation
  and media decoding
- Optional: an NVIDIA GPU with CUDA — speeds up transcription and thumbnail
  generation, but everything also runs on CPU
- The `[transcribe]` extra (`faster-whisper`) if you intend to transcribe
  media locally

Run `kb doctor` at any time to check which of these are present.

## Quickstart

```bash
git clone https://github.com/OWNER/meetingkb.git
cd meetingkb
pip install -e ".[transcribe,dev]"

# Start OpenSearch (Docker)
docker compose -f deploy/docker-compose.yml up -d

# Check your environment (ffmpeg, docker, python, faster-whisper, GPU)
kb doctor

# Transcribe media in the data directory, build the index, then serve
kb transcribe
kb index
kb serve
```

`kb up` chains the same steps (start OpenSearch, index, generate
thumbnails, serve) into a single command for a quick end-to-end bootstrap.
Note: `kb up` invokes `deploy/docker-compose.yml` as a path relative to the
repo root, and `deploy/` is not included in the packaged wheel — so `kb up`
only works from a cloned repo checkout, not from a bare `pip install`. Use
the explicit `docker compose -f deploy/docker-compose.yml up -d` step above
instead if you installed from a wheel/PyPI.

### Try it with the bundled sample data (no Docker/GPU needed)

The repo ships tiny, non-personal demo transcripts under `sample_data/` so
you can explore the UI without any real recordings, Docker, or a GPU:

```bash
KB_DATA_DIR=./sample_data KB_TERMS_FILE=./sample_data/terms.txt kb index --no-opensearch
KB_DATA_DIR=./sample_data KB_TERMS_FILE=./sample_data/terms.txt kb serve
```

On Windows PowerShell:

```powershell
$env:KB_DATA_DIR = "./sample_data"
$env:KB_TERMS_FILE = "./sample_data/terms.txt"
kb index --no-opensearch
kb serve
```

See [sample_data/README.md](sample_data/README.md) for details on the demo
fixtures.

## Configuration

All settings are `KB_`-prefixed environment variables (or a `.env` file in
the working directory), backed by `meetingkb.config.Settings`. Copy
[.env.example](.env.example) to `.env` and adjust as needed.

| Variable | Default | Description |
| --- | --- | --- |
| `KB_DATA_DIR` | `./data` | Root directory for media, transcripts, and the SQLite database. |
| `KB_OPENSEARCH_URL` | `http://127.0.0.1:9200` | OpenSearch endpoint used for full-text search. |
| `KB_LANGUAGE` | `en` | Language hint passed to the transcriber. |
| `KB_TERMS_FILE` | *(none)* | Path to a file of glossary terms (one per line) to detect per meeting. |
| `KB_LLM_BASE_URL` | `http://127.0.0.1:11434/v1` | Base URL of an OpenAI-compatible chat endpoint (e.g. Ollama, vLLM). |
| `KB_LLM_MODEL` | *(empty)* | Model name to request from the LLM endpoint; required to use "ask". |
| `KB_LLM_API_KEY` | *(empty)* | API key sent as a bearer token, if the endpoint requires one. |
| `KB_UI_PORT` | `8502` | Port the Streamlit UI listens on. |
| `KB_WHISPER_MODEL` | `medium` | `faster-whisper` model size/name used for transcription. |
| `KB_WHISPER_DEVICE` | `auto` | Device for transcription: `auto`, `cpu`, or `cuda`. |
| `KB_INITIAL_PROMPT` | *(empty)* | Optional Whisper initial prompt (e.g. to bias vocabulary). |

`transcript_dir` and `db_path` are derived from `KB_DATA_DIR` when not set
explicitly, and are not meant to be overridden independently in normal use.

## CLI reference

| Command | Description |
| --- | --- |
| `kb transcribe [PATH]` | Transcribe media files that don't have a transcript yet (default: `KB_DATA_DIR`). |
| `kb index [--no-opensearch]` | Build the SQLite (and, by default, OpenSearch) meeting index. |
| `kb thumbnails` | Generate seek-bar hover-preview thumbnails for meetings missing them. |
| `kb serve [--port PORT]` | Launch the Streamlit UI. |
| `kb up` | Start OpenSearch (Docker Compose), index, generate thumbnails, then serve — an end-to-end bootstrap. |
| `kb doctor` | Check the local environment for required and optional tooling (ffmpeg, Docker, Python version, `faster-whisper`, GPU). |
| `kb version` | Print the installed MeetingKB version. |

## Screenshots

Screenshots are not included yet — see
[docs/screenshots/README.md](docs/screenshots/README.md) for why and how
they'll be added. In the meantime, the fastest way to see the UI is the
[sample-data demo](#try-it-with-the-bundled-sample-data-no-dockergpu-needed)
above — it's fully self-contained and takes under a minute to set up.

## License

MIT — see [LICENSE](LICENSE).

---

Repository URLs in `pyproject.toml` use an `OWNER` placeholder; set it to
the real GitHub owner/organization before publishing.
