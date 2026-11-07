# Personal Voice Replication & Expressive TTS Manager (`voice-replication`)

A Python 3.13 library and dual-mode Rich/Typer CLI (`voice-rep`) for creating, persisting, auditing, and synthesising speech with personal replicated voices and companion Voice Design personas using Google's **Gemini 3.8 Flash TTS** (`gemini-3.8-flash-tts` and `gemini-3.8-flash-lite-tts`) and **Google Cloud Storage** (`<your-project>`).

![Architecture Overview](docs/images/architecture.png)

## Repo Metadata

- **Author**: Darren "Dazbo" Lester (`derailed-dash`)
- **Language & Runtime**: Python 3.13 (`uv`)
- **Target GCP Project**: `<your-project>` (`europe-west2` London)

## Table of Contents

- [Key Project Documentation](#key-project-documentation)
- [Key Links & Official References](#key-links--official-references)
- [Features](#features)
- [Project Structure](#project-structure)
- [Architecture and Tech Stack - at a Glance](#architecture-and-tech-stack---at-a-glance)
- [Quick Start: Working With This Repo](#quick-start:working-with-this-repo)
- [End-to-End Usage Walkthrough](#end-to-end-usage-walkthrough)
- [Useful Commands](#useful-commands)
- [Verification, Rubrics & Loopy TDD Workflow](#verification-rubrics--loopy-tdd-workflow)
- [Troubleshooting](#troubleshooting)

## Key Project Documentation

| Document | Description |
| :--- | :--- |
| [README.md](README.md) | Developer front door, quick start, CLI reference, and official documentation links |
| [SPEC.md](SPEC.md) | Complete system specification, boundaries, and acceptance criteria |
| [LOOPS.md](LOOPS.md) | Repeatable Loopy + TDD vertical slice loop definition |
| [TODO.md](TODO.md) | Ordered project task list and verification checkpoints |
| [tasks/plan.md](tasks/plan.md) | Technical implementation plan, dependency mapping, and risk register |
| [docs/architecture-and-walkthrough.md](docs/architecture-and-walkthrough.md) | Architectural Decision Records (ADRs), storage class analysis, and data models |
| [docs/testing.md](docs/testing.md) | Two-tier verification strategy, TDD cycle, and test suite guide |
| [deployment/README.md](deployment/README.md) | GCP project security preflight, Coldline bucket provisioning, and `git-crypt` setup |

## Key Links & Official References

### Google AI Studio & Gemini API Documentation

- [Gemini API — Voice Replication Guide](https://aistudio.google.com/docs/voice-replication) — Stateful (`store=True`) vs stateless (`store=False`) voice replication, consent phrases by language, and best practices for 24kHz mono WAV reference audio.
- [Gemini API — Speech Generation (TTS) Guide](https://aistudio.google.com/docs/speech-generation) — Single-speaker and multi-speaker synthesis, turn-level `speech_metadata` styling, inline vocal tags, and Studio voices.
- [Gemini API — Voice Design Guide](https://aistudio.google.com/docs/voice-design) — Creating persistent custom vocal personas (`type="prompted"`) from natural-language descriptions.
- [Gemini API — Audio Transcription (`gemini-3.5-transcribe`)](https://aistudio.google.com/docs/transcribe) — Verbatim and smart speech-to-text recognition across 85+ locales.
- [Gemini API — Interactions API Overview](https://aistudio.google.com/docs/interactions-overview) — Unified `client.interactions.create` surface for text, audio, and multimodal generation.
- [Google AI Studio — Generate Speech Playground](https://aistudio.google.com/generate-speech) — Interactive browser studio for auditioning voices and testing prompts.

### Google Cloud Storage & Security Documentation

- [Google Cloud Storage — Storage Classes](https://docs.cloud.google.com/storage/docs/storage-classes) — At-rest pricing, minimum storage durations (30d Nearline, 90d Coldline, 365d Archive), and millisecond retrieval characteristics.
- [Google Cloud Storage — Pricing](https://cloud.google.com/storage/pricing) — Storage, Class A/B operations, retrieval, and early-deletion fee breakdown.
- [Google Cloud Storage — Autoclass Overview](https://docs.cloud.google.com/storage/docs/autoclass) — Automated object transitions and `128 KiB` minimum object size rules.
- [Google Cloud Storage — Uniform Bucket-Level Access (UBLA)](https://cloud.google.com/storage/docs/uniform-bucket-level-access) — Standardising access control around IAM.
- [Google Cloud Storage — Public Access Prevention](https://cloud.google.com/storage/docs/public-access-prevention) — Enforcing private-only bucket access.
- [Google Cloud Storage — Soft Delete](https://cloud.google.com/storage/docs/soft-delete) — Protecting against accidental object or bucket deletion.
- [Google Cloud Storage — Enforce Encryption Types](https://cloud.google.com/storage/docs/encryption/enforce-encryption-types) — Restricting Customer-Supplied Encryption Keys (CSEK).

## Features

- **Automated Audio Pre-Flight (`prep-audio`)**: Converts any raw recording (`.m4a`, `.mp3`, `.wav`, `.ogg`, stereo, 44.1/48kHz) into the recommended **24kHz mono 16-bit PCM WAV** format using `ffmpeg`, validates the mandatory **10.0–30.0 second** reference duration via `ffprobe`, supports start/end trimming (`--trim-start`, `--trim-end`), and verifies that your consent clip recites the mandatory consent statement using `gemini-3.5-transcribe`.
- **Multi-Tier Voice Persistence (`<your-project>`)**:
  - **Gemini API Stateful Storage (`store=True`)**: Stores your verified `voice_...` profile in `<your-project>` (up to 200 custom voices per project, **1-year retention TTL**).
  - **Stateless Client-Managed Keys (`store=False`)**: Optionally issues encrypted `voicekey_...` tokens (**7-day TTL**) for zero server-side storage.
  - **Cost-Optimised GCS Backup (`europe-west2`)**: Syncs your master 24kHz `.wav` recordings to a private Regional GCS bucket using the **`COLDLINE`** default storage class (\$0.004/GiB/month, millisecond access) while explicitly overriding `voices.json` to **`STANDARD`** storage class so frequent metadata updates never trigger Coldline 90-day early-deletion charges.
- **Voice Design Co-Hosts (`design`)**: Creates persistent synthetic voices (`type="prompted"`) from natural-language descriptions to pair with your replicated voice in dialogues.
- **Single-Speaker & Multi-Speaker TTS (`speak`, `dialogue`)**: Synthesises inline text, Markdown monologues (`.md`/`.txt`), or multi-speaker YAML dialogue scripts (`.yaml`) with turn-level `speech_metadata` style instructions and exports `.wav` or `.mp3`.
- **Agent-Aware Dual-Mode CLI**: Every command supports `--json` for deterministic agent parsing, and every mutating command supports `--dry-run` for safe validation.

## Project Structure

```text
voice-replication/
├── deployment/
│   └── README.md                   # GCP security preflight, Coldline bucket setup & git-crypt guide
├── docs/
│   ├── images/
│   │   └── architecture.png        # System architecture diagram
│   ├── architecture-and-walkthrough.md # ADRs, storage class rationale, and component design
│   └── testing.md                  # TDD loop, static gates, and test suite reference
├── examples/
│   ├── dialogue.yaml               # Sample two-speaker podcast dialogue script
│   └── monologue.md                # Sample single-speaker narration script with vocal tags
├── src/
│   └── voice_replication/
│       ├── __init__.py             # Public library exports
│       ├── audio.py                # ffmpeg/ffprobe 24kHz mono WAV normalisation & MP3 export
│       ├── cli.py                  # Typer + Rich agent-aware CLI (voice-rep)
│       ├── client.py               # Gemini Voices & Interactions API wrapper
│       ├── config.py               # Pydantic Settings (.env / environment configuration)
│       ├── consent.py              # Consent phrase registry & gemini-3.5-transcribe verifier
│       ├── models.py               # Pydantic schemas (VoiceRecord, VoiceCatalogue, DialogueScript)
│       └── storage.py              # Local voices.json registry & GCS Coldline/Standard sync
├── tasks/
│   └── plan.md                     # Implementation plan and dependency breakdown
├── tests/                          # Offline pytest unit & integration suite
├── .env.template                   # Committed environment variable template
├── .gitattributes                  # git-crypt encryption rules for .env.enc
├── .gitignore                      # Excludes .env, data/, output/, and raw audio files
├── LOOPS.md                        # Saved Loopy TDD vertical slice loop
├── Makefile                        # Self-documenting automation (.DEFAULT_GOAL := help)
├── pyproject.toml                  # Python 3.13 + uv package and tool configuration
├── README.md                       # This file
├── SPEC.md                         # Project specification
└── TODO.md                         # Project task checklist
```

## Architecture and Tech Stack - at a Glance

| Layer | Technology | Role |
| :--- | :--- | :--- |
| **Runtime & Packaging** | Python `>=3.13`, `uv`, `hatchling` | Fast, reproducible virtual environment and CLI entrypoint (`voice-rep`) |
| **Speech & Voice API** | `google-genai >= 2.30.1` | `client.voices` (`POST /v1beta/voices`) & `client.interactions.create` (`gemini-3.8-flash-tts`, `gemini-3.8-flash-lite-tts`, `gemini-3.5-transcribe`) |
| **Cloud Backup** | `google-cloud-storage >= 3.0.0` | Regional (`europe-west2`) bucket sync (`COLDLINE` default for `.wav` + `STANDARD` override for `voices.json`) |
| **Audio Engine** | `ffmpeg` & `ffprobe` | Resampling to 24kHz mono 16-bit PCM WAV (`pcm_s16le`), duration checks, trimming, and `libmp3lame` MP3 encoding |
| **CLI & Validation** | `typer`, `rich`, `pydantic`, `pydantic-settings`, `pyyaml` | Dual-mode human TUI tables and agent-friendly `--json` / `--dry-run` commands |

See [docs/architecture-and-walkthrough.md](docs/architecture-and-walkthrough.md) for full Architectural Decision Records (ADRs) and data flow details.

## Quick Start: Working With This Repo

### Prerequisites

1. **Python 3.13 & `uv`**: Installed at `/usr/local/bin/uv` or `~/.local/bin/uv`.
2. **`ffmpeg` & `ffprobe`**: Installed via system package manager (`sudo apt install ffmpeg`).
3. **Google Cloud SDK (`gcloud`)**: Authenticated with Application Default Credentials (`gcloud auth application-default login`) for project `<your-project>`.
4. **Gemini API Key**: Created in [Google AI Studio](https://aistudio.google.com/apikey) and linked to the **`<your-project>`** GCP project.

### One-Time Setup

```bash
# 1. Install Python dependencies and dev tooling into .venv
make install

# 2. Create your local .env from the template and populate GEMINI_API_KEY
cp .env.template .env

# 3. Inspect and run the GCS Bucket Architect preflight & bucket creation in <your-project>
uv run voice-rep gcs-preflight
uv run voice-rep gcs-init --dry-run
# When ready to provision gs://<voice-name>-voice-replication in europe-west2:
uv run voice-rep gcs-init
```

### Per Dev Session

```bash
# Verify the full static + unit test gate (codespell, ruff, pyright, pytest)
make check

# View available CLI commands
uv run voice-rep --help
```

## End-to-End Usage Walkthrough

### 1. Record & Normalise Your Reference and Consent Clips

Record two clips on the **same microphone in the same quiet room**:

1. **Reference clip (`raw_ref.m4a`)**: 10–30 seconds of natural, expressive speech.
2. **Consent clip (`raw_consent.m4a`)**: Clearly recite the mandatory English statement:
   > *"I am the owner of this voice and I consent to Google using this voice to create a synthetic voice model."*

Normalise both clips to **24kHz mono 16-bit PCM WAV** and run the `gemini-3.5-transcribe` pre-flight check:

```bash
uv run voice-rep prep-audio raw_ref.m4a raw_consent.m4a --alias dazbo
```

### 2. Create Your Persistent Replicated Voice & Sync to GCS

Register your voice in `<your-project>` (`store=True`, 1-year TTL) and back up the registry (`STANDARD`) + master WAVs (`COLDLINE`) to GCS:

```bash
uv run voice-rep create \
  --alias dazbo \
  --display-name "Dazbo Primary" \
  --default-style "warm, articulate British technical presenter"

# Back up voices.json and master 24kHz WAVs to gs://<voice-name>-voice-replication
uv run voice-rep sync --direction push
```

### 3. Synthesise Single-Speaker & Multi-Speaker Audio

```bash
# Inline single-speaker synthesis to MP3
uv run voice-rep speak \
  "Hello! This audio was synthesised using my replicated voice on Gemini 3.8 Flash TTS." \
  --voice dazbo \
  --style "cheerful and conversational" \
  --output output/greeting.mp3

# Markdown monologue script to WAV
uv run voice-rep speak \
  --file examples/monologue.md \
  --voice dazbo \
  --output output/monologue.wav

# Multi-speaker dialogue from YAML (pairing 'dazbo' with prebuilt Studio voice 'Kore')
uv run voice-rep dialogue examples/dialogue.yaml --output output/podcast_intro.mp3
```

### 4. Inspect & Refresh Voices Before 1-Year TTL Expiry

```bash
# View local catalogue and remaining TTL days
uv run voice-rep list

# Renew a voice's 1-year TTL from local/GCS master WAVs
uv run voice-rep refresh dazbo
uv run voice-rep sync --direction push
```

## Useful Commands

| Command | Description |
| :--- | :--- |
| `make` or `make help` | Show all self-documenting `Makefile` targets and configurable variables |
| `make install` | Sync virtual environment and install all runtime + dev dependencies via `uv` |
| `make lint` / `make fix` | Run `codespell`, `ruff`, and `pyright` (or auto-fix formatting with `make fix`) |
| `make test` / `make test-live` | Run offline `pytest` suite (`>=85%` coverage gate) or live Gemini API smoke tests |
| `make check` | Run full Tier 1 verification gate (`codespell` + `ruff` + `pyright` + `pytest`) |
| `make prep-audio SOURCE=<ref> CONSENT=<con>` | Normalise audio to 24kHz mono WAV, check 10–30s duration, and verify consent via STT |
| `make create [ALIAS=dazbo]` | Create a stateful (`store=True`, 1-year TTL) replicated voice in Gemini API |
| `make create-stateless [ALIAS=dazbo]` | Create a stateless (`store=False`, 7-day TTL) `voice_key` token |
| `make design ALIAS=cohost PROMPT="..."` | Create a persistent Voice Design (`type="prompted"`) co-host persona |
| `make list` / `make list-remote` | List local voice aliases, IDs, and TTL countdown (plus optional remote API voices) |
| `make inspect [ALIAS=dazbo]` | Inspect full metadata, TTL countdown, and audio paths for a voice alias |
| `make refresh [ALIAS=dazbo]` | Re-create a replicated voice from cached/GCS WAVs to renew its 1-year TTL |
| `make delete` / `make delete-remote` | Delete a voice from the local catalogue (and optionally from Gemini API) |
| `make speak [FILE=...] [OUT=...]` | Synthesise single-speaker speech (`FILE=examples/monologue.md` or `TEXT="..."`) |
| `make dialogue [SCRIPT=...] [OUT=...]` | Synthesise multi-speaker dialogue from YAML (`examples/dialogue.yaml`) |
| `make gcs-preflight` / `make gcs-init` | Print `gcloud` security pre-flight commands or provision `gs://<voice-name>-voice-replication` |
| `make sync-push` / `make sync-pull` / `make sync` | Sync `voices.json` (`STANDARD`) and master WAVs (`COLDLINE`) with GCS |

## Verification, Rubrics & Loopy TDD Workflow

This repository uses a bounded **Loopy + TDD Vertical Slice** workflow (`Observe -> Choose -> Act -> Verify -> Record -> Stop`) defined in [LOOPS.md](LOOPS.md) and detailed in [docs/testing.md](docs/testing.md):

1. **Red -> Green -> Refactor Slice Execution**: Each slice in [TODO.md](TODO.md) begins with a failing `pytest` test before production code is written, modifying one semantic behaviour per pass.
2. **Tier 1 Mechanical Gate (`make check`, \$0 Cost)**: Runs `codespell`, `ruff check`, `pyright`, and `pytest --cov` (`>=85%` coverage gate). Any failure short-circuits immediately before semantic review.
3. **Tier 2 Stateless Semantic Rubric (`B1`–`B7`)**: Once Tier 1 passes, a fresh stateless `research` Critic subagent (without builder history) audits the repository against 7 binary `PASS`/`FAIL` assertions (`B1`–`B7`) defined in [SPEC.md](SPEC.md) and [docs/testing.md](docs/testing.md).
4. **Circuit Breakers & Receipts**: Loops stop when 100% of Tier 1 and Tier 2 (`B1`–`B7`) checks pass, after 5 passes per slice, or after 2 consecutive passes without progress, recording pass deltas in `.cache/loops/last_receipt.md`.

## Troubleshooting

### Error: `Reference audio duration is X.XXs; Gemini Voice Replication requires between 10.0s and 30.0s`

**Cause**: Your source recording is shorter than 10 seconds or longer than 30 seconds.

**Solution**: Trim the recording during normalisation using `--trim-start` and `--trim-end`:

```bash
uv run voice-rep prep-audio long_recording.m4a consent.m4a --alias dazbo --trim-start 1.5 --trim-end 25.0
```

### Error: `Consent transcript similarity (XX.XX%) below threshold`

**Cause**: `gemini-3.5-transcribe` detected words that differ from the mandatory consent statement, or background noise obscured speech.

**Solution**: Re-record `consent.wav` on the same microphone reciting the exact phrase (*"I am the owner of this voice and I consent to Google using this voice to create a synthetic voice model."*), or pass `--no-verify-consent` if a proper noun/accent caused a false-negative STT diff.
