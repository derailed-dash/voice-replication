"""Unit tests for mandatory consent statement lookup and STT verification (`consent.py`)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from voice_replication.consent import (
    DEFAULT_ENGLISH_CONSENT_PHRASE,
    compute_phrase_similarity,
    get_consent_phrase,
    verify_consent_audio,
)


@dataclass
class _FakeInteractionResponse:
    output_text: str


class _FakeInteractionsResource:
    def __init__(self, transcript: str) -> None:
        self.transcript = transcript
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> _FakeInteractionResponse:
        self.calls.append(kwargs)
        return _FakeInteractionResponse(output_text=self.transcript)


class _FakeGenAIClient:
    def __init__(self, transcript: str) -> None:
        self.interactions = _FakeInteractionsResource(transcript)


class TestConsentPhrasesAndSimilarity:
    """Verify consent phrase lookup across locales and word-similarity scoring."""

    def test_english_consent_phrase_lookup(self) -> None:
        assert get_consent_phrase("en-GB") == DEFAULT_ENGLISH_CONSENT_PHRASE
        assert get_consent_phrase("en-US") == DEFAULT_ENGLISH_CONSENT_PHRASE
        assert "owner of this voice" in get_consent_phrase("en")

    def test_unknown_language_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unsupported consent language code"):
            get_consent_phrase("xx-INVALID")

    def test_compute_similarity_exact_and_near_match(self) -> None:
        exact = compute_phrase_similarity(
            DEFAULT_ENGLISH_CONSENT_PHRASE,
            (
                "I am the owner of this voice, and I consent to Google "
                "using this voice to create a synthetic voice model!"
            ),
        )
        assert exact == pytest.approx(1.0)

        wrong = compute_phrase_similarity(
            DEFAULT_ENGLISH_CONSENT_PHRASE,
            "Testing one two three microphone check.",
        )
        assert wrong < 0.35


class TestVerifyConsentAudio:
    """Verify `gemini-3.5-transcribe` STT pre-flight check against `consent.wav`."""

    def test_verify_consent_audio_passes_on_matching_transcript(
        self, sample_consent_wav: Path
    ) -> None:
        fake_client = _FakeGenAIClient(
            "I am the owner of this voice and I consent to Google "
            "using this voice to create a synthetic voice model."
        )
        result = verify_consent_audio(
            sample_consent_wav,
            client=fake_client,
            language_code="en-GB",
        )
        assert result.passed is True
        assert result.similarity == pytest.approx(1.0)
        assert len(fake_client.interactions.calls) == 1
        call_kwargs = fake_client.interactions.calls[0]
        assert call_kwargs["model"] == "gemini-3.5-transcribe"
        assert call_kwargs["input"][0]["type"] == "audio"
        assert call_kwargs["input"][0]["mime_type"] == "audio/wav"

    def test_verify_consent_audio_fails_on_mismatched_transcript(
        self, sample_consent_wav: Path
    ) -> None:
        fake_client = _FakeGenAIClient("Hello world, this is my reference recording.")
        result = verify_consent_audio(
            sample_consent_wav,
            client=fake_client,
            language_code="en-GB",
        )
        assert result.passed is False
        assert result.similarity < 0.5
