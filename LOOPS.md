# Project loops

## TDD Vertical Slice Loop

Implements one unchecked task slice from [TODO.md](TODO.md) using strict Red-Green-Refactor TDD, deterministic Tier 1 static/test gates, and a final Tier 2 stateless semantic review (`B1`–`B7`), stopping when all acceptance criteria pass or when no progress occurs across two passes.

Prompt:
> Observe the next unchecked slice in `TODO.md` and its contract in `SPEC.md`. Write failing `pytest` tests in `tests/` first and run `uv run pytest` to confirm the RED failure. Implement the minimal production code in `src/voice_replication/` to turn tests GREEN, then refactor and run `make check` (`codespell`, `ruff`, `pyright`, `pytest --cov`). Record pass evidence in `.cache/loops/last_receipt.md` and `TODO.md`. Once all slices pass Tier 1 (`make check`), spawn a fresh stateless `research` subagent (without builder history) to audit the repository against the 7 binary Tier 2 Semantic Rubric assertions (`B1`: PEP 585/604 typing & module docstrings; `B2`: `gemini-3.8-flash-tts` / `gemini-3.8-flash-lite-tts` / `gemini-3.5-transcribe` via `client.voices.*` & `client.interactions.create`; `B3`: 24kHz mono `pcm_s16le` WAV & 10.0–30.0s duration guard; `B4`: GCS `europe-west2` `COLDLINE` default + `STANDARD` override on `voices.json`; `B5`: `--json` on all CLI commands, `--dry-run` on mutating commands, actionable `stderr` hints; `B6`: UK English, blank line after headings, relative links only, embedded `docs/images/architecture.png`, official Google/GCS doc links; `B7`: `.gitignore` & `.gitattributes` secret/audio hygiene). Stop when 100% of Tier 1 and Tier 2 (`B1`–`B7`) checks pass, after 5 passes per slice, or after 2 consecutive passes without progress. Ask before adding dependencies, running mutating `gcloud` or remote delete commands, or committing to Git.

Saved: 2026-11-07
