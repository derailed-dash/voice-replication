# Testing, Rubrics, and Loop Verification (`voice-replication`)

This document explains how iterative Test-Driven Development (TDD), the two-tier verification rubric, and bounded agent loops (`loopy`) work together in this repository.

## Table of Contents

- [Loop Architecture (`Observe -> Choose -> Act -> Verify -> Record -> Stop`)](#loop-architecture-observe---choose---act---verify---record---stop)
- [Two-Tier Verification Gate & Short-Circuiting](#two-tier-verification-gate--short-circuiting)
- [Tier 1 Deterministic Mechanical Gate (`make check`)](#tier-1-deterministic-mechanical-gate-make-check)
- [Tier 2 Stateless Semantic Rubric (`B1`–`B7`)](#tier-2-stateless-semantic-rubric-b1b7)
- [Circuit Breaker Trio & Receipt Persistence](#circuit-breaker-trio--receipt-persistence)
- [Test Suite Structure](#test-suite-structure)
- [Test Doubles & Offline Isolation](#test-doubles--offline-isolation)
- [Live API Smoke Testing](#live-api-smoke-testing)

## Loop Architecture (`Observe -> Choose -> Act -> Verify -> Record -> Stop`)

Development and maintenance in this repository follow the **TDD Vertical Slice Loop** saved in [LOOPS.md](../LOOPS.md). Rather than writing large batches of unverified code, every feature or bug fix executes as a bounded, repeatable loop over vertical slices tracked in [TODO.md](../TODO.md):

1. **Observe**: Read the next unchecked `[ ]` vertical slice in [TODO.md](../TODO.md) and its behavioural contract in [SPEC.md](../SPEC.md).
2. **Choose (The One-Change Rule)**: Select **one semantic behaviour** to implement or fix in the current pass so any regression is immediately attributable.
3. **Act (Red -> Green -> Refactor)**:
   - **RED**: Write or update the `pytest` unit/integration test in `tests/` first and run `uv run pytest` to confirm the expected failure.
   - **GREEN**: Write the minimal production code in `src/voice_replication/` required to make the test pass. Never weaken a test or alter the verification oracle to manufacture a pass.
   - **REFACTOR**: Clean up duplication, docstrings, and type annotations while keeping tests green.
4. **Verify (Two-Tier Gate)**: Run the Tier 1 mechanical gate (`make check`) after every slice, and run the Tier 2 Stateless Semantic Critic once all slices pass Tier 1.
5. **Record**: Log the pass delta (`Before -> After`), coverage, and evidence in `.cache/loops/last_receipt.md` (git-ignored) and mark completed tasks `[x]` in [TODO.md](../TODO.md).
6. **Stop**: Halt immediately when the target gate is met or when any circuit breaker trips.

## Two-Tier Verification Gate & Short-Circuiting

To prevent wasted token burn and eliminate self-grading bias, verification is split into two ordered tiers with **strict short-circuiting**:

- **Short-Circuit Rule**: Tier 1 runs first at **\$0 API cost** in `<4` seconds. If any Tier 1 check (`codespell`, `ruff`, `pyright`, or `pytest --cov`) fails, the loop **short-circuits immediately** and returns to the `Act` phase to fix the mechanical defect before any semantic review is attempted.
- **Stateless Critic Isolation**: Only when 100% of Tier 1 checks pass does the loop spawn a **fresh, stateless `research` subagent** (with zero builder conversation history) to grade the repository against the Tier 2 binary rubric (`B1`–`B7`). Using a clean context window prevents the agent that wrote the code from rationalising shortcuts.

## Tier 1 Deterministic Mechanical Gate (`make check`)

Run the complete Tier 1 gate with a single command:

```bash
make check
```

| Check ID | Tool | Command | Pass Criterion |
| :--- | :--- | :--- | :--- |
| **T1.1** | **codespell** | `uv run codespell -s` | `0` spelling mistakes across `src/`, `tests/`, `examples/`, and `*.md` |
| **T1.2** | **ruff** | `uv run ruff check --fix .` | `0` lint, import-sorting (`I`), modern Python 3.13 (`UP`), or bugbear (`B`) violations |
| **T1.3** | **pyright** | `uv run pyright` | `0` static type errors across `src/` and `tests/` |
| **T1.4** | **pytest** | `uv run pytest -m "not live" --cov=voice_replication` | 100% of unit/integration tests pass with `>=85%` total line coverage |

## Tier 2 Stateless Semantic Rubric (`B1`–`B7`)

Unlike vague 1–10 rating scales, the Tier 2 Semantic Rubric uses **7 strict binary (`PASS`/`FAIL`) assertions** codified in [SPEC.md](../SPEC.md) and [LOOPS.md](../LOOPS.md). A single `FAIL` returns the loop to the `Act` phase with the Critic's exact file/line citation:

| Rubric ID | Dimension | Binary `PASS` / `FAIL` Assertion |
| :--- | :--- | :--- |
| **`B1`** | **Modern Python 3.13 & Module Docstrings** | Every `.py` file in `src/voice_replication/` and `tests/` has a top-of-module docstring and uses PEP 585/604 built-in generics (`list[...]`, `dict[...]`, `X \| None`) with zero imports of `List`, `Dict`, `Optional`, `Tuple`, or `Union` from `typing`. |
| **`B2`** | **Latest Gemini Models & Interactions API** | Uses `gemini-3.8-flash-tts`, `gemini-3.8-flash-lite-tts`, and `gemini-3.5-transcribe` via `google-genai` (`client.voices.*` and `client.interactions.create`), with zero usage of legacy `generateContent` or downgraded models. |
| **`B3`** | **Audio Pre-Flight & Duration Guard** | [src/voice_replication/audio.py](../src/voice_replication/audio.py) normalises input audio to **24kHz (`24000` Hz), mono (`1` channel), 16-bit PCM WAV (`pcm_s16le`)** and strictly enforces the **10.0s to 30.0s** reference duration window. |
| **`B4`** | **GCS Storage-Class-Aware Persistence** | [src/voice_replication/storage.py](../src/voice_replication/storage.py) configures the bucket in `europe-west2` with `COLDLINE` default storage class (`--uniform-bucket-level-access`, `--public-access-prevention`, `--soft-delete-duration=7d`) and explicitly overrides `voices.json` to `STANDARD` storage class (`blob.storage_class = "STANDARD"`) on upload while keeping `.wav` blobs on `COLDLINE`. |
| **`B5`** | **Agent-Aware CLI Ergonomics** | Every CLI command in [src/voice_replication/cli.py](../src/voice_replication/cli.py) supports `--json` (emitting valid JSON on `stdout`), mutating commands (`prep-audio`, `create`, `design`, `refresh`, `delete`, `speak`, `dialogue`, `gcs-init`, `sync`) support `--dry-run`, and errors emit actionable hints on `stderr`. |
| **`B6`** | **Documentation & Visual Standards** | Core documentation ([README.md](../README.md), [docs/architecture-and-walkthrough.md](architecture-and-walkthrough.md), [docs/testing.md](testing.md), [deployment/README.md](../deployment/README.md)) uses UK English, has a blank line after every markdown heading, uses relative paths (zero `file:///` URIs), embeds the generated PNG diagram ([docs/images/architecture.png](images/architecture.png)) with zero Mermaid/ASCII diagrams, and links to all official Google AI Studio & GCS documentation. |
| **`B7`** | **Security & Secret Hygiene** | [.gitignore](../.gitignore) excludes `.env`, `data/`, `output/`, `*.wav`/`*.mp3`/`*.m4a`/`*.ogg`, and `.cache/`, and [.gitattributes](../.gitattributes) configures `git-crypt` (`*.enc filter=git-crypt diff=git-crypt`). |

## Circuit Breaker Trio & Receipt Persistence

Every autonomous loop run enforces three hard stopping conditions:

1. **Target Gate (`target_met`)**: 100% of Tier 1 (`T1.1`–`T1.4`) and Tier 2 (`B1`–`B7`) checks pass (`7 / 7 PASS`).
2. **Budget Cap (`budget_exhausted`)**: Maximum **5 passes** per vertical slice.
3. **Stall Detector (`stalled`)**: Trips the circuit breaker and escalates to the user if the pass score fails to improve across **2 consecutive passes**.

At the end of each loop run, the structured evidence table is written to `.cache/loops/last_receipt.md` (git-ignored) and printed in chat as a **Loopy Run Receipt**.

## Test Suite Structure

| Test File | Module Under Test | Key Scenarios Verified |
| :--- | :--- | :--- |
| [tests/conftest.py](../tests/conftest.py) | Shared Fixtures | Deterministic 16-bit PCM sine-wave WAV generator (`generate_sine_wav`) for arbitrary sample rates, channels, and durations |
| [tests/test_models.py](../tests/test_models.py) | `config.py`, `models.py` | `Settings` defaults, `AudioStats` 24kHz/10–30s properties, `VoiceRecord` 365d stateful vs 7d stateless TTL math, `VoiceCatalogue` CRUD, and `DialogueScript` YAML validation |
| [tests/test_audio.py](../tests/test_audio.py) | `audio.py` | Real `ffprobe` stream inspection, real `ffmpeg` resampling from 48kHz stereo to 24kHz mono `pcm_s16le` WAV, `--trim-start`/`--trim-end` slicing, duration bounds, and `.mp3` export |
| [tests/test_consent.py](../tests/test_consent.py) | `consent.py` | Locale consent phrase lookup, punctuation-insensitive word similarity scoring, and `gemini-3.5-transcribe` verification pass/fail handling |
| [tests/test_client.py](../tests/test_client.py) | `client.py` | Stateful (`store=True`) and stateless (`store=False`) voice replication payloads, Voice Design (`type="prompted"`) preview saving, remote CRUD, and single/multi-speaker TTS payloads |
| [tests/test_storage.py](../tests/test_storage.py) | `storage.py` | Atomic `voices.json` persistence, GCS `push` (`STANDARD` on `voices.json`, `COLDLINE` on `.wav` clips), GCS `pull` workspace restore, and attributed `gcloud` command generation |
| [tests/test_cli.py](../tests/test_cli.py) | `cli.py` | All 12 `voice-rep` CLI subcommands across `--dry-run`, `--json`, human Rich tables, and `stderr` remediation hints |

## Test Doubles & Offline Isolation

- **Real Local Media Tools**: `tests/test_audio.py` invokes the actual `/usr/bin/ffmpeg` and `/usr/bin/ffprobe` binaries against synthetic sine-wave `.wav` files generated in `tmp_path` so codec and filter regressions are caught immediately.
- **Injected Cloud Fakes**: `VoiceReplicationClient` and `GCSBackupManager` accept optional `client` / `storage_client` constructor parameters, allowing `pytest` to verify exact request payloads and storage class assignments offline at \$0 cost in `<4` seconds.

## Live API Smoke Testing

Once `.env` is populated with a valid `GEMINI_API_KEY` and your audio files are prepared:

```bash
# 1. Verify dry-run payload generation first
make speak TEXT="Testing live synthesis." ALIAS=Kore FLAGS="--dry-run --json"

# 2. Run a live synthesis call using a prebuilt Studio voice or your replicated voice alias
make speak TEXT="Hello! Gemini 3.8 Flash TTS is live." ALIAS=Kore OUT=output/smoke_test.mp3
```
