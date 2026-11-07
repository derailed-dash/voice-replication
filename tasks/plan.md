# Implementation Plan: Personal Voice Replication & TTS Manager (`voice-replication`)

## Overview

We are building a Python 3.13 package (`voice_replication`) and dual-mode Rich/Typer CLI (`voice-rep`) that manages personal voice replication and speech synthesis using `gemini-3.8-flash-tts`, `gemini-3.8-flash-lite-tts`, and `gemini-3.5-transcribe`, backed by stateful Gemini API voice persistence (`store=True`) and a Regional (`europe-west2`) GCS backup bucket in `<your-project>` (`COLDLINE` default storage class + `STANDARD` override for `voices.json`). Tasks are tracked in [TODO.md](../TODO.md) and executed via the **TDD Vertical Slice Loop** defined in [LOOPS.md](../LOOPS.md).

## Architecture Decisions

| Decision | Choice | Rationale |
| :--- | :--- | :--- |
| **Voice Persistence** | Gemini API `store=True` + Local `data/voices.json` + GCS Backup | `store=True` persists the verified `voice_...` profile in `<your-project>` for 1 year; local/GCS registry maps human-friendly aliases (`dazbo`) and preserves master 24kHz WAVs for 1-command TTL refresh. |
| **GCS Storage Class Strategy** | Regional (`europe-west2`) `COLDLINE` default + `STANDARD` override for `voices.json` | Master `.wav` files (~1.5 MB) are written once and read rarely (on TTL refresh or new machine sync), fitting Coldline (\$0.004/GiB/mo, 90d min duration, millisecond access), while `voices.json` (~2 KB) is updated on every voice change and uses `STANDARD` to avoid early-deletion fees. |
| **Audio Normalisation & Consent Pre-flight** | `ffmpeg` (24kHz mono 16-bit PCM WAV) + `ffprobe` (10–30s check) + `gemini-3.5-transcribe` | Eliminates speaker-verification rejections caused by mismatched sample rates, stereo channels, invalid durations, or misread consent statements before calling `voices.create()`. |
| **CLI UX (`agent-aware-cli`)** | `typer` + `rich` with `--json`, `--dry-run`, and `NO_COLOR` support | Serves human operators with Tufte-style Rich tables and autonomous coding agents with deterministic JSON payloads and mutative dry-run safety. |

## Dependency Graph

| Slice | Module / Target | Depends On |
| :--- | :--- | :--- |
| **Slice 1** | `pyproject.toml`, `Makefile`, `config.py`, `models.py` | None |
| **Slice 2** | `audio.py` (`ffmpeg` / `ffprobe` 24kHz mono WAV & MP3) | Slice 1 |
| **Slice 3** | `consent.py` (`gemini-3.5-transcribe` verification) | Slice 1, Slice 2 |
| **Slice 4** | `client.py` (`client.voices` CRUD & `gemini-3.8-flash-tts`) | Slice 1 |
| **Slice 5** | `storage.py` (Local `voices.json` & GCS Coldline/Standard sync) | Slice 1 |
| **Slice 6** | `cli.py` & `examples/` (Typer/Rich `--json` & `--dry-run` CLI) | Slices 1–5 |
| **Slice 7** | Core Documentation (`README.md`, `docs/`, `deployment/`) & Tier 2 Critic | Slice 6 |

## Task Index (Tracked in [TODO.md](../TODO.md))

### Phase 1: Foundation & Audio Pipeline

- Task 1: Repository Scaffolding, `pyproject.toml`, `Makefile`, `.env.template`, and Config/Domain Models (`config.py`, `models.py`)
- Task 2: Audio Inspection, 24kHz Mono WAV Normalisation, Trimming, and MP3 Export (`audio.py`)
- Task 3: Consent Statement Table & `gemini-3.5-transcribe` Pre-flight Verification (`consent.py`)

### Checkpoint 1: Foundation & Audio Pipeline

- Verify `make check` passes for Tasks 1–3.

### Phase 2: Gemini API Client, Storage Sync & CLI

- Task 4: Gemini Voices CRUD & Single/Multi-Speaker TTS Synthesis Client (`client.py`)
- Task 5: Local Catalogue Persistence, GCS Security Preflight, and Storage-Class-Aware Sync (`storage.py`)
- Task 6: Dual-Mode Rich/Typer CLI (`cli.py`) & Example Scripts (`examples/`)

### Checkpoint 2: Full Feature Suite

- Verify `make check` passes with `>=85%` coverage across all modules.

### Phase 3: Documentation & Tier 2 Critic Verification

- Task 7: Core Documentation (`README.md`, `docs/architecture-and-walkthrough.md`, `docs/testing.md`, `deployment/README.md`) & Visual Architecture Diagram
- Task 8: Tier 2 Stateless Semantic Critic Audit & Final Loopy Run Receipt

## Risks and Mitigations

| Risk | Impact | Mitigation |
| :--- | :--- | :--- |
| Speaker verification failure on `voices.create` | Medium | Enforce 24kHz mono 16-bit PCM WAV via `ffmpeg`, validate 10–30s duration via `ffprobe`, and verify consent transcript via `gemini-3.5-transcribe` before submission. |
| GCS early deletion charges on frequently updated `voices.json` | Low | Explicitly set `blob.storage_class = "STANDARD"` when uploading `voices.json`, while leaving `.wav` blobs on the bucket's `COLDLINE` default. |
| `gcloud` or API calls during unit test execution | High | Inject fake/stub `genai.Client`, `storage.Client`, and subprocess runners in unit tests so `make check` runs 100% offline in `<5s`. |
