# Project Plan: Personal Voice Replication & TTS Manager (`voice-replication`)

- [x] Complete `/grill-me` requirements discovery and approve [SPEC.md](SPEC.md) and [LOOPS.md](LOOPS.md) (2026-11-07)

## Phase 1: Foundation & Audio Pipeline

- [x] **Task 1: Repository Scaffolding, Config & Domain Models (`config.py`, `models.py`)** (2026-11-07)
  - **Acceptance**:
    - `pyproject.toml`, self-documenting `Makefile` (`.DEFAULT_GOAL := help`), `.env.template`, `.gitignore`, and `.gitattributes` created and `uv sync` installs cleanly.
    - `Settings` loads `.env` / env vars (`GEMINI_API_KEY`, `GCP_PROJECT_ID`, `GCS_BUCKET_NAME`, `GCS_LOCATION`, `DEFAULT_VOICE_ALIAS`, `DEFAULT_TTS_MODEL`).
    - `VoiceRecord`, `VoiceCatalogue`, `AudioStats`, `DialogueTurn`, and `DialogueScript` validate schemas, compute 1-year stateful / 7-day stateless TTL expiry, and parse YAML/Markdown scripts.
  - **Verify**: `uv run pytest tests/test_models.py` and `make lint`
  - **Files**: `pyproject.toml`, `Makefile`, `.env.template`, `.gitignore`, `.gitattributes`, `src/voice_replication/__init__.py`, `src/voice_replication/config.py`, `src/voice_replication/models.py`, `tests/conftest.py`, `tests/test_models.py`

- [x] **Task 2: Audio Inspection, 24kHz Mono WAV Normalisation & MP3 Export (`audio.py`)** (2026-11-07)
  - **Acceptance**:
    - `inspect_audio()` uses `ffprobe` to extract sample rate, channels, codec, and duration.
    - `normalise_audio()` uses `ffmpeg` to resample/convert any input audio to 24kHz mono 16-bit PCM WAV (`pcm_s16le`), supporting optional `trim_start` and `trim_end`.
    - `validate_reference_duration()` enforces the 10.0–30.0s window for `source_audio`.
    - `export_mp3()` converts generated WAV files to MP3 via `ffmpeg`.
  - **Verify**: `uv run pytest tests/test_audio.py` (using real `ffmpeg`/`ffprobe` on synthetic sine-wave WAVs in `tmp_path`)
  - **Files**: `src/voice_replication/audio.py`, `tests/test_audio.py`

- [x] **Task 3: Consent Phrase Registry & `gemini-3.5-transcribe` Verification (`consent.py`)** (2026-11-07)
  - **Acceptance**:
    - Contains canonical consent phrases by language (`en-US` / `en-GB` default: *"I am the owner of this voice and I consent to Google using this voice to create a synthetic voice model."*).
    - Normalises punctuation/casing and computes word-level similarity score against expected consent text.
    - `verify_consent_audio()` calls `client.interactions.create(model="gemini-3.5-transcribe", ...)` on `consent.wav` and returns structured verification result (`passed`, `transcript`, `similarity`).
  - **Verify**: `uv run pytest tests/test_consent.py`
  - **Files**: `src/voice_replication/consent.py`, `tests/test_consent.py`

### Checkpoint 1: Foundation & Audio Pipeline

- [x] All tests in `tests/test_models.py`, `tests/test_audio.py`, and `tests/test_consent.py` pass via `make check`. (2026-11-07)

## Phase 2: Gemini API Client, Storage Sync & CLI

- [x] **Task 4: Gemini Voices CRUD & TTS Synthesis Client (`client.py`)** (2026-11-07)
  - **Acceptance**:
    - `create_replicated_voice()` calls `client.voices.create()` for both stateful (`store=True` -> `voice_...`) and stateless (`store=False` -> `voicekey_...`) modes.
    - `create_designed_voice()` calls `client.voices.create(voice={"type": "prompted", ...})` for synthetic co-hosts.
    - `list_remote_voices()`, `get_remote_voice()`, and `delete_remote_voice()` wrap `client.voices.list/get/delete`.
    - `synthesise_single_speaker()` and `synthesise_dialogue()` call `client.interactions.create()` with `speech_metadata` annotations and decode the returned base64 WAV audio.
  - **Verify**: `uv run pytest tests/test_client.py`
  - **Files**: `src/voice_replication/client.py`, `tests/test_client.py`

- [x] **Task 5: Local Catalogue & GCS Storage-Class-Aware Backup (`storage.py`)** (2026-11-07)
  - **Acceptance**:
    - Saves and loads `data/voices.json` atomically and manages `data/audio/<alias>/{source.wav,consent.wav}`.
    - `sync_to_gcs()` uploads `.wav` files using the bucket's `COLDLINE` default storage class and explicitly overrides `voices.json` to `STANDARD` storage class.
    - `sync_from_gcs()` pulls `voices.json` and missing `.wav` files into the local cache.
    - Generates attributed `gcloud` preflight and bucket creation commands per `google-cloud-storage-bucket-architect` (`europe-west2`, `COLDLINE`, UBLA, PAP, 7-day soft delete, restricted CSEK).
  - **Verify**: `uv run pytest tests/test_storage.py`
  - **Files**: `src/voice_replication/storage.py`, `tests/test_storage.py`

- [x] **Task 6: Agent-Aware Rich/Typer CLI (`cli.py`) & Examples (`examples/`)** (2026-11-07)
  - **Acceptance**:
    - Implements `prep-audio`, `create`, `design`, `list`, `inspect`, `refresh`, `delete`, `speak`, `dialogue`, `gcs-preflight`, `gcs-init`, and `sync` commands.
    - Supports `--json` on all commands, `--dry-run` on all mutating commands, and actionable error hints on `stderr`.
    - Includes sample scripts in `examples/monologue.md` and `examples/dialogue.yaml`.
  - **Verify**: `uv run pytest tests/test_cli.py` and `make check`
  - **Files**: `src/voice_replication/cli.py`, `examples/monologue.md`, `examples/dialogue.yaml`, `tests/test_cli.py`

### Checkpoint 2: Full Feature Suite

- [x] `make check` (`codespell`, `ruff`, `pyright`, `pytest --cov`) passes with `>=85%` test coverage. (2026-11-07)

## Phase 3: Documentation & Tier 2 Critic Verification

- [x] **Task 7: Core Documentation & Architecture Diagram (`maintaining-core-documentation`)** (2026-11-07)
  - **Acceptance**:
    - Generate a visual PNG architecture diagram (`docs/images/architecture.png`) and embed via relative link (no Mermaid or ASCII diagrams).
    - Create `README.md` (with all referenced official Google AI Studio & GCS documentation links), `docs/architecture-and-walkthrough.md`, `docs/testing.md`, and `deployment/README.md` following `maintaining-core-documentation` formatting rules (blank line after every heading).
  - **Verify**: `uvx codespell@latest -s` and structural markdown validation.
  - **Files**: `README.md`, `docs/architecture-and-walkthrough.md`, `docs/testing.md`, `deployment/README.md`, `docs/images/architecture.png`

- [x] **Task 8: Tier 2 Stateless Semantic Critic Audit & Loopy Receipt** (2026-11-07)
  - **Acceptance**:
    - Stateless `research` subagent audits codebase against binary `PASS`/`FAIL` criteria from [SPEC.md](SPEC.md).
    - Record final run receipt in `.cache/loops/last_receipt.md` and output Loopy receipt.
  - **Verify**: 100% of Tier 1 and Tier 2 checks pass.

## Phase 4: Live Voice Replication, Multi-Speaker Dialogue & Documentation Synchronisation

- [x] **Task 9: Multi-Speaker Scenarios, Collaborator Sharing & Documentation Synchronisation** (2026-11-07)
  - **Acceptance**:
    - Default `speak` and `dialogue` outputs to `.mp3` (`output/speech.mp3`, `output/dialogue.mp3`) and automatically remove temporary `.wav` files after MP3 encoding.
    - Organise raw recordings in `data/raw/` and personal YAML dialogue scripts in `data/scripts/` (git-ignored under `data/`).
    - Update [README.md](README.md) with step-by-step `make` CLI vs Google AI Studio instructions for single-speaker replication, multi-speaker replication (`dazbo` + `kate`), single-speaker TTS, multi-speaker dialogue synthesis, and collaborator project sharing.
    - Update [deployment/README.md](deployment/README.md) with full GCP project creation, all 3 required API enablements (`generativelanguage.googleapis.com`, `storage.googleapis.com`, `apikeys.googleapis.com`), IAM collaborator sharing for Google AI Studio, and shared `git-crypt` key usage (`~/localdev/git-crypt-key`).
  - **Verify**: `uv run codespell -s` and structural markdown validation.
  - **Files**: `README.md`, `deployment/README.md`, `TODO.md`
