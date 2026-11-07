# Spec: Personal Voice Replication & TTS Manager (`voice-replication`)

## Objective

Build a Python 3.13 library and Rich/Typer CLI (`voice-rep`) for creating, persisting, auditing, and synthesising speech with personal replicated voices (and companion Voice Design personas) using Google's Gemini 3.8 TTS models (`gemini-3.8-flash-tts` and `gemini-3.8-flash-lite-tts`) via the Interactions & Voices APIs.

The project solves three core problems:
1. **Reliable Audio Preparation & Consent Pre-Flight**: Automatically normalising raw microphone recordings (`.m4a`, `.mp3`, `.wav`, etc.) to **24kHz mono 16-bit PCM WAV** via `ffmpeg`, enforcing the 10–30 second reference audio window, and pre-verifying the mandatory consent statement with `gemini-3.5-transcribe` before calling `client.voices.create()`.
2. **Multi-Tier Persistence in `<your-project>`**: Persisting stateful voice models (`store=True`, `voice_...`, 1-year TTL) in the `<your-project>` GCP project, paired with a local git-ignored registry (`data/voices.json` + `data/audio/`) backed up to a secure Regional GCS bucket in `europe-west2` (`COLDLINE` default storage class for rare-read master `.wav` clips and `STANDARD` per-object storage class override for `voices.json`).
3. **Expressive Single- and Multi-Speaker Synthesis**: Generating single-speaker narration and multi-speaker dialogue scripts (YAML/Markdown) with turn-level `speech_metadata` style instructions, inline vocal tags, and `.wav` / `.mp3` output.

## Tech Stack

- **Language & Runtime**: Python `>=3.13`, managed exclusively via `uv` (`pyproject.toml`)
- **Google AI & Cloud SDKs**:
  - `google-genai >= 2.30.1` (`client.voices` for Voice Replication / Voice Design CRUD; `client.interactions.create` for `gemini-3.8-flash-tts`, `gemini-3.8-flash-lite-tts`, and `gemini-3.5-transcribe`)
  - `google-cloud-storage >= 3.0.0` (GCS bucket backup, restore, and storage-class-aware object uploads)
- **CLI, Config & Validation**:
  - `typer >= 0.15.0` & `rich >= 13.9.0` (Dual-mode human TUI + agent-aware `--json` and `--dry-run` output)
  - `pydantic >= 2.10.0` & `pydantic-settings >= 2.7.0` (`.env` configuration and `voices.json` catalogue schema)
  - `pyyaml >= 6.0.2` (Multi-speaker dialogue script parsing)
- **System Binaries**:
  - `ffmpeg` & `ffprobe` (`/usr/bin/ffmpeg`, `/usr/bin/ffprobe`) for 24kHz mono 16-bit PCM WAV normalisation, duration inspection, trimming, and MP3 export
  - `gcloud` CLI for GCS bucket security preflight and provisioning (`google-cloud-storage-bucket-architect`)
  - `git-crypt` for encrypting `.env` (`secrets-with-git-crypt`)
- **Quality & Static Gates**:
  - `pytest`, `pytest-cov`, `ruff`, `pyright`, `codespell`

## Commands

```bash
# Project Automation (Makefile defaults to help)
make                  # Display self-documenting help target
make install          # Sync uv virtual environment (uv sync --all-extras)
make lint             # Run codespell, ruff check, and pyright
make fix              # Auto-fix formatting and lint issues via ruff
make test             # Run unit tests with pytest and coverage
make check            # Full deterministic Tier 1 gate (codespell + ruff + pyright + pytest)

# Audio Preparation & Pre-flight Check
uv run voice-rep prep-audio raw_ref.m4a raw_consent.m4a --alias dazbo --trim-end 28.0 --verify-consent

# Voice Replication & Voice Design CRUD
uv run voice-rep create --alias dazbo --display-name "Dazbo Primary" \
  --source data/audio/dazbo/source.wav --consent data/audio/dazbo/consent.wav \
  --default-style "warm, articulate British presenter"
uv run voice-rep design --alias cohost --display-name "Tech Co-Host" \
  --prompt "A bright, inquisitive studio podcast co-host with a crisp cadence."
uv run voice-rep list [--remote] [--json]
uv run voice-rep inspect dazbo [--json]
uv run voice-rep refresh dazbo [--dry-run]
uv run voice-rep delete dazbo [--remote] [--dry-run]

# Speech Synthesis (Single-Speaker & Multi-Speaker Dialogue)
uv run voice-rep speak "Hello! Welcome to today's technical deep dive." \
  --voice dazbo --style "cheerful and conversational" --output output/intro.mp3
uv run voice-rep speak --file scripts/monologue.md --voice dazbo --output output/monologue.wav
uv run voice-rep dialogue scripts/podcast_episode.yaml --output output/episode.mp3

# Cloud Storage Provisioning & Backup Sync (<your-project>)
uv run voice-rep gcs-preflight [--json]
uv run voice-rep gcs-init [--dry-run]
uv run voice-rep sync [--direction push|pull|both] [--dry-run] [--json]
```

## Project Structure

```text
voice-replication/
├── Makefile                        # Self-documenting automation (.DEFAULT_GOAL := help)
├── pyproject.toml                  # Python 3.13 + uv dependency and tool configuration
├── .env.template                   # Committed template for GEMINI_API_KEY, GCP_PROJECT_ID, GCS_BUCKET_NAME
├── .gitignore                      # Ignores .env, data/, output/, .venv/
├── .gitattributes                  # git-crypt rules for .env.enc / secret files
├── SPEC.md                         # Project specification (source of truth)
├── LOOPS.md                        # Saved repeatable Loopy TDD & verification loops
├── TODO.md                         # Task breakdown and progress tracker
├── README.md                       # Documentation, architecture, usage, and official reference links
├── examples/
│   ├── monologue.md                # Sample single-speaker script with inline vocal tags
│   └── dialogue.yaml               # Sample multi-speaker dialogue script
├── src/
│   └── voice_replication/
│       ├── __init__.py             # Public library exports
│       ├── config.py               # Pydantic Settings (.env / environment loader)
│       ├── models.py               # Pydantic schemas (VoiceRecord,VoiceCatalogue, DialogueScript, AudioStats)
│       ├── audio.py                # ffmpeg/ffprobe normalisation (24kHz mono 16-bit WAV), trimming, MP3 export
│       ├── consent.py              # Consent phrase table & gemini-3.5-transcribe verification
│       ├── client.py               # Gemini API wrapper (voices.create/list/get/delete, TTS interactions.create)
│       ├── storage.py              # Local voices.json registry + GCS sync (COLDLINE WAVs + STANDARD voices.json)
│       └── cli.py                  # Typer + Rich agent-aware CLI (human TUI tables + --json / --dry-run)
└── tests/
    ├── conftest.py                 # Shared fixtures (synthetic WAV generator, mocked GenAI/GCS clients)
    ├── test_models.py              # Schema, TTL calculation, and dialogue parsing tests
    ├── test_audio.py               # ffmpeg/ffprobe conversion, duration validation, and MP3 export tests
    ├── test_consent.py             # Consent statement similarity and STT verification tests
    ├── test_client.py              # Voices CRUD, stateless keys, single/multi-speaker TTS payload tests
    ├── test_storage.py             # Local catalogue persistence & GCS storage-class upload/download tests
    └── test_cli.py                 # Typer CLI invocation tests (--json, --dry-run, error hints)
```

## Code Style

All modules include a top-of-module docstring explaining purpose, value, and mechanics, use UK English spelling in comments/docs, and adhere strictly to PEP 585 / PEP 604 type hinting (`list[str]`, `dict[str, Any]`, `str | None`):

```python
"""Gemini Voices and TTS Interactions API client wrapper.

Provides typed methods for creating stateful (`store=True`) and stateless
(`store=False`) replicated voices, designing prompted voices, and synthesising
single- or multi-speaker audio via `gemini-3.8-flash-tts`.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from google import genai


def build_single_speaker_payload(
    text: str,
    voice_id_or_key: str,
    *,
    model: str = "gemini-3.8-flash-tts",
    style: str | None = None,
) -> dict[str, Any]:
    """Construct the Interactions API request dictionary for single-speaker TTS."""
    content_item: dict[str, Any] = {"type": "text", "text": text}
    if style:
        content_item["annotations"] = [{"type": "speech_metadata", "style": style}]

    return {
        "model": model,
        "input": [{"type": "user_input", "content": [content_item]}],
        "response_format": {"type": "audio"},
        "generation_config": {
            "speech_config": [{"voice": voice_id_or_key}],
        },
    }
```

## Testing Strategy & Loopy + TDD Execution Architecture

We combine **`test-driven-development`** (`Red -> Green -> Refactor`) with **`loopy`** (`Observe -> Choose -> Act -> Verify -> Record -> Stop`) across every implementation slice:

1. **Saved Project Loop ([LOOPS.md](LOOPS.md))**:
   - Defines the repeatable **TDD Vertical Slice Loop** for this repository so any slice or future feature follows the same bounded feedback cycle.
2. **Per-Slice Red-Green-Refactor Cycle (The One-Change Rule)**:
   - **Observe**: Read the next unchecked slice in [TODO.md](TODO.md) and corresponding section in [SPEC.md](SPEC.md).
   - **Choose**: Select one vertical slice (`config/models` → `audio` → `consent` → `client` → `storage` → `cli`).
   - **Act (RED → GREEN → REFACTOR)**:
     1. **RED**: Write the `pytest` unit/integration tests for the slice first (`uv run pytest tests/test_<slice>.py`) and confirm they fail for the expected reason.
     2. **GREEN**: Implement the minimal production code in `src/voice_replication/<slice>.py` to make the tests pass (one semantic behaviour per pass).
     3. **REFACTOR**: Clean up types, docstrings, and duplication while keeping tests green.
3. **Two-Tier Verification Gate (Short-Circuiting)**:
   - **Tier 1 — Deterministic Mechanical Gate (Run First, \$0 Cost)**:
     - `uvx codespell@latest -s`
     - `uvx ruff@latest check --fix .`
     - `uv run pyright`
     - `uv run pytest --cov=voice_replication` (via `make check`).
     - If any Tier 1 check fails, short-circuit immediately and fix before moving on.
   - **Tier 2 — Stateless Semantic Critic (Fresh Context)**:
     - Once all slices pass Tier 1, invoke a fresh, stateless `research` subagent (or `local-code-review` pass) without builder history to evaluate the codebase against the 7 binary `PASS`/`FAIL` assertions (`B1`–`B7`) derived from the Success Criteria in [SPEC.md](SPEC.md):
       - **`B1` (Modern Python 3.13 & Module Docstrings)**: All `.py` files in `src/voice_replication/` and `tests/` have top-of-module docstrings and use PEP 585/604 built-in generics (`list[...]`, `dict[...]`, `X | None`) without importing `List`, `Dict`, `Optional`, `Tuple`, or `Union` from `typing`.
       - **`B2` (Latest Gemini Models & Interactions API)**: Uses `gemini-3.8-flash-tts`, `gemini-3.8-flash-lite-tts`, and `gemini-3.5-transcribe` via `google-genai` (`client.voices.*` and `client.interactions.create`), with zero usage of legacy `generateContent` or downgraded models.
       - **`B3` (Audio Pre-Flight & Duration Guard)**: `audio.py` normalises input audio to **24kHz (`24000` Hz), mono (`1` channel), 16-bit PCM WAV (`pcm_s16le`)** and strictly enforces the **10.0s to 30.0s** reference duration window.
       - **`B4` (GCS Storage-Class-Aware Persistence)**: `storage.py` configures the bucket in `europe-west2` (`<your-project>`) with `COLDLINE` default storage class (`--uniform-bucket-level-access`, `--public-access-prevention`, `--soft-delete-duration=7d`) and explicitly overrides `voices.json` to `STANDARD` storage class (`blob.storage_class = "STANDARD"`) on upload while keeping `.wav` blobs on `COLDLINE`.
       - **`B5` (Agent-Aware CLI Ergonomics)**: Every CLI command in `cli.py` supports `--json` (emitting valid JSON on `stdout`), mutating commands (`prep-audio`, `create`, `design`, `refresh`, `delete`, `speak`, `dialogue`, `sync`) support `--dry-run`, and errors emit actionable hints on `stderr`.
       - **`B6` (Documentation & Visual Standards)**: Core documentation (`README.md`, `docs/architecture-and-walkthrough.md`, `docs/testing.md`, `deployment/README.md`) uses UK English, has a blank line after every markdown heading, uses relative paths (zero `file:///` URIs), embeds the generated PNG diagram (`docs/images/architecture.png`) with zero Mermaid/ASCII diagrams, and links to all referenced official Google AI Studio & GCS documentation.
       - **`B7` (Security & Secret Hygiene)**: `.gitignore` excludes `.env`, `data/`, `output/`, and `.cache/`, and `.gitattributes` configures `git-crypt` for `.env.enc`.
4. **Circuit Breaker Trio (Stopping Conditions)**:
   - **Target Gate**: 100% of Tier 1 and Tier 2 binary assertions pass (`>=85%` test coverage).
   - **Budget Cap**: Maximum **4–5 passes** per slice.
   - **Stall Detector**: Trip the circuit breaker and escalate if the pass rate fails to improve across **2 consecutive passes**.
5. **Iteration Memory & Receipts**:
   - Record each pass's evidence and score deltas in `.cache/loops/last_receipt.md` (git-ignored) and output a structured **Loopy run receipt** upon completion.
- **Test Doubles & Isolation**:
  - `test_audio.py` runs real `ffmpeg` / `ffprobe` against tiny synthetically generated sine-wave `.wav` files in `tmp_path` to verify 24kHz mono 16-bit PCM conversion, duration checks, and `.mp3` export deterministically.
  - `test_client.py`, `test_consent.py`, and `test_storage.py` use dependency-injected fakes/stubs for `genai.Client` and `google.cloud.storage.Client` so `make check` runs 100% offline at \$0 cost.
  - Optional live smoke tests (marked `@pytest.mark.live`) can be run on demand once `.env` and audio files are in place.

## Boundaries

- **Always Do**:
  - Follow TDD (Red-Green-Refactor) for every module.
  - Run the 3-part deterministic static gate (`codespell`, `ruff`, `pyright`) plus `pytest` after changes.
  - Use UK English in all documentation, CLI output, and docstrings.
  - Keep `.env`, `data/`, and `output/` git-ignored so biometric voice recordings and API keys are never committed in plaintext.
  - Prefix any `gcloud` storage commands with the required `CLOUDSDK_METRICS_ENVIRONMENT` attribution header from the GCS skills.
- **Ask First**:
  - Adding any dependency beyond those listed in Tech Stack above.
  - Executing mutating `gcloud storage buckets create` or deleting remote voices/buckets in `<your-project>`.
  - Running `git commit` or `git push`.
- **Never Do**:
  - Downgrade Gemini model strings (always use `gemini-3.8-flash-tts`, `gemini-3.8-flash-lite-tts`, `gemini-3.5-transcribe`).
  - Use legacy `google-generativeai` or `generateContent` endpoints.
  - Use `file:///` URIs in markdown links or documentation.
  - Swallow generic `Exception` blocks silently or hardcode credentials.

## Success Criteria

1. `make check` (`codespell`, `ruff`, `pyright`, `pytest`) passes with 0 errors and `>=85%` test coverage.
2. `voice-rep prep-audio` converts input audio to 24kHz mono 16-bit PCM WAV, validates the 10–30s reference duration window, and checks the consent statement against the canonical English consent text via `gemini-3.5-transcribe`.
3. `voice-rep create` and `voice-rep design` register voices via `client.voices.create()`, record metadata and 1-year TTL expiry in `data/voices.json`, and support `--stateless` (`store=False`, 7-day `voicekey_...`).
4. `voice-rep sync` backs up and restores master `.wav` files (`COLDLINE` storage class) and `voices.json` (`STANDARD` storage class override) to/from the regional `europe-west2` GCS bucket in `<your-project>`.
5. `voice-rep speak` and `voice-rep dialogue` synthesise single-speaker and multi-speaker audio via `client.interactions.create()` and save `.wav` or `.mp3` files.
6. Every CLI command supports `--json` (for agent consumption) and mutating commands support `--dry-run` with actionable error hints.
7. `README.md` documents the full workflow, architecture, GCS storage class rationale, and links to all official Google AI Studio and Google Cloud documentation.

## Open Questions

None — all architectural, storage class, and feature decisions were resolved during the `/grill-me` design interview.
