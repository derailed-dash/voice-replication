# Project Rules & Agent Context: `voice-replication`

This repository contains the codebase for **`voice-replication` (`voice-rep`)** — a Python 3.13 library and Agent-Aware CLI for personal voice replication, biometric consent verification, voice design, multi-speaker speech synthesis, and regional Google Cloud Storage (GCS) backup using the Gemini 3.8 Speech Generation (TTS) and Interactions APIs.

---

## 1. Reference Material & Mandatory Reading

### External Reference Documentation

- **Gemini Voice Replication & Voice Design**: https://aistudio.google.com/docs/voice-replication
- **Gemini Speech Generation (TTS)**: https://ai.google.dev/gemini-api/docs/speech-generation
- **Gemini Interactions API**: https://ai.google.dev/gemini-api/docs/interactions

### Repository Specifications & Core Docs

Before making architectural or behavioural changes, inspect:

- [`SPEC.md`](SPEC.md) — Canonical functional specification, CLI exit code contract, and the **Tier 2 Binary Semantic Rubric (`B1`–`B7`)**.
- [`LOOPS.md`](LOOPS.md) — Autonomous verification loop definition (`voice-replication-quality-gate`), circuit breaker rules, and Tier 1 + Tier 2 gate commands.
- [`README.md`](README.md) — Setup, workflow walkthroughs, `Makefile` targets, and CLI command reference.
- [`docs/architecture-and-walkthrough.md`](docs/architecture-and-walkthrough.md) — Architecture Decision Records (ADRs 1–6) and component blueprint.
- [`docs/testing.md`](docs/testing.md) — Unit/CLI test coverage matrix and two-tier verification workflow.
- [`deployment/README.md`](deployment/README.md) — GCP API enablement, IAM permissions, and `COLDLINE` + `STANDARD` GCS storage provisioning.

---

## 2. General & Python Standards

- **Language**: Use English (UK) spelling in all documentation, code comments, and user-facing CLI text (`initialise`, `normalise`, `synthesise`, `catalogue`, `behaviour`).
- **Relative Links Only**: NEVER use `file:///` URI paths in markdown files or responses; always use relative repository paths (e.g. [`SPEC.md`](SPEC.md)).
- **Python & Tooling**:
  - Target **Python >= 3.13**, managed via `uv` and [`pyproject.toml`](pyproject.toml).
  - Use strict modern PEP 585 & PEP 604 type annotations (`list[str]`, `dict[str, Any]`, `str | None`). Never import `List`, `Dict`, `Optional`, `Tuple`, or `Union` from `typing`.
  - Include top-of-module docstrings in every `.py` file explaining purpose, value, and mechanics.

---

## 3. Gemini Model & SDK Invariants (NEVER Downgrade)

- **SDK**: Exclusively use `google-genai >= 2.30.1`. Never use deprecated `google-generativeai` or legacy `generate_content` calls where the Interactions API is supported.
- **Models**:
  - **Default High-Expressivity TTS, Voice Replication & Voice Design**: `gemini-3.8-flash-tts`
  - **Low-Cost / High-Throughput TTS**: `gemini-3.8-flash-lite-tts`
  - **Consent Verification ASR Transcription**: `gemini-3.5-transcribe`
- **API Surfaces**:
  - **Voice Management (`src/voice_replication/client.py`)**:
    - `client.voices.create(config={...})` (`store=True` stateful vs `store=False` stateless, or prompt-based Voice Design)
    - `client.voices.list()`
    - `client.voices.get(name="voice-...")`
    - `client.voices.delete(name="voice-...")`
  - **Speech Synthesis & Transcription**:
    - `client.interactions.create(model=..., input=..., config=types.GenerateContentConfig(...))` with `response_modalities=["AUDIO"]` and `types.SpeechConfig` / `types.MultiSpeakerVoiceConfig`.

---

## 4. Domain & Architectural Guardrails (`B1`–`B7`)

All code changes must preserve the 7 binary semantic invariants defined in [`SPEC.md`](SPEC.md):

1. **`B1` — SDK & Model Compliance**: Uses `google-genai` (`client.voices.*` and `client.interactions.create`) with `gemini-3.8-flash-tts`, `gemini-3.8-flash-lite-tts`, and `gemini-3.5-transcribe`.
2. **`B2` — Consent Gate Enforcement (`src/voice_replication/consent.py`)**: Voice replication (`create`) requires a verified `ConsentRecord(verified=True)` produced by transcribing the speaker's consent audio via `gemini-3.5-transcribe` and verifying a normalised `SequenceMatcher` similarity ratio >= `0.85` against the required consent statement.
3. **`B3` — Audio Format & Duration Bounds (`src/voice_replication/audio.py`)**: All prepared reference and consent clips and synthesised WAV outputs are 24,000 Hz, 16-bit, mono PCM WAV files, with replication/consent clips strictly bounded between `10.0s` and `30.0s`.
4. **`B4` — Dual-Mode Agent-Aware CLI (`src/voice_replication/cli.py`)**: Every CLI command supports `--json` (emitting a single valid JSON object to `stdout` and routing logs/errors to `stderr`), mutating commands support `--dry-run`, and failures map to deterministic exit codes (`0`, `2`, `3`, `4`, `5`, `130`).
5. **`B5` — Stateful vs Stateless & TTL Lifecycle (`src/voice_replication/models.py`)**: Registry tracks `store=True` stateful handles (`voice-...` with 7-day rolling `expires_at` refreshed on `get` / synthesis / `refresh`) alongside `store=False` stateless voices and designed voices.
6. **`B6` — GCS Security & Cost-Tiered Storage (`src/voice_replication/storage.py`)**: Enforces regional bucket (`europe-west2`), Uniform Bucket-Level Access (`uniform_bucket_level_access_enabled = True`), Public Access Prevention (`public_access_prevention = "enforced"`), `COLDLINE` default bucket storage class for rare-read `.wav` files, and explicit `blob.storage_class = "STANDARD"` override when uploading `voices.json`.
7. **`B7` — Modern Python 3.13 Standards & Documentation Integrity**: PEP 585/604 typing, module docstrings, no `mermaid` or ASCII diagrams in docs (use generated PNGs in `docs/images/`), and no `file:///` links.

---

## 5. Security & Public-Repository Hygiene

- **Sanitised `.env.template` & Tracked Files**: Keep personal GCP project IDs, bucket names, voice aliases, and API keys strictly in `.env` (git-ignored) and [`.env.enc`](.env.enc) (`git-crypt` encrypted). Tracked code, [`Makefile`](Makefile), [`.env.template`](.env.template), and documentation must use generic placeholders (`<your-project>`, `<voice-name>-voice-replication`, `<voice-name>`).
- **Shared `git-crypt` Key**: This repository is unlocked using the shared symmetric key at `~/localdev/git-crypt-key`. Always run `git-crypt-helper.sh status` (and `sync-from-enc` if `.env.enc` is newer) before editing `.env`, and run `sync-to-enc .env` before committing secret updates.
- **Makefile Variable Safety**: Never use `NAME ?=` or `LANG ?=` in [`Makefile`](Makefile) (which collide with WSL/Linux `$NAME` and `$LANG`); use `DISPLAY_NAME ?=` and `LANGUAGE ?=`.

---

## 6. Verification & Testing Workflow

Run the full Tier 1 verification gate from the repository root after any code or documentation change:

```bash
make check
```

Which executes:

```bash
uv run codespell -s
uv run ruff check --fix .
uv run pyright
uv run pytest -m "not live" --cov=voice_replication --cov-report=term-missing
```
