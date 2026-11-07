"""Consent phrase catalogue and `gemini-3.5-transcribe` verification (`consent.py`).

Validates that the speaker's consent audio recording clearly recites the
mandatory Gemini Voice Replication consent statement before calling
`client.voices.create()`.
"""

from __future__ import annotations

import base64
import difflib
import re
from pathlib import Path
from typing import Any

from voice_replication.models import ConsentCheckResult

DEFAULT_ENGLISH_CONSENT_PHRASE = (
    "I am the owner of this voice and I consent to Google using this voice "
    "to create a synthetic voice model."
)

CONSENT_PHRASES_BY_LANGUAGE: dict[str, str] = {
    "en": DEFAULT_ENGLISH_CONSENT_PHRASE,
    "en-GB": DEFAULT_ENGLISH_CONSENT_PHRASE,
    "en-US": DEFAULT_ENGLISH_CONSENT_PHRASE,
    "en-AU": DEFAULT_ENGLISH_CONSENT_PHRASE,
    "en-IN": DEFAULT_ENGLISH_CONSENT_PHRASE,
    "de-DE": (
        "Ich bin der Eigentümer dieser Stimme und stimme zu, dass Google "
        "diese Stimme verwendet, um ein synthetisches Sprachmodell zu erstellen."
    ),
    "es-ES": (
        "Soy el propietario de esta voz y doy mi consentimiento para que Google "
        "la utilice para crear un modelo de voz sintética."
    ),
    "es-US": (
        "Soy el propietario de esta voz y doy mi consentimiento para que Google "
        "la utilice para crear un modelo de voz sintética."
    ),
    "fr-FR": (
        "Je suis le propriétaire de cette voix et j'autorise Google à utiliser "
        "cette voix pour créer un modèle de voix synthétique."
    ),
    "it-IT": (
        "Sono il proprietario di questa voce e acconsento che Google la utilizzi "
        "per creare un modello di voce sintetica."
    ),
    "ja-JP": (
        "私はこの音声の所有者であり、Googleがこの音声を使用して"
        "音声合成モデルを作成することを承認します。"
    ),
    "pt-BR": (
        "Eu sou o proprietário desta voz e autorizo o Google a usá-la para "
        "criar um modelo de voz sintética."
    ),
}

DEFAULT_SIMILARITY_THRESHOLD = 0.88


def get_consent_phrase(language_code: str = "en-GB") -> str:
    """Return the official mandatory consent phrase for `language_code`."""
    if language_code in CONSENT_PHRASES_BY_LANGUAGE:
        return CONSENT_PHRASES_BY_LANGUAGE[language_code]
    msg = (
        f"Unsupported consent language code '{language_code}'. "
        f"Supported codes: {sorted(CONSENT_PHRASES_BY_LANGUAGE.keys())}"
    )
    raise ValueError(msg)


def _normalise_words(text: str) -> list[str]:
    """Lowercase and strip punctuation from `text`, returning a list of words."""
    cleaned = re.sub(r"[^\w\s]", "", text.lower(), flags=re.UNICODE)
    return cleaned.split()


def compute_phrase_similarity(expected: str, actual: str) -> float:
    """Compute normalised word-sequence similarity ratio in `[0.0, 1.0]`."""
    expected_words = _normalise_words(expected)
    actual_words = _normalise_words(actual)
    if not expected_words and not actual_words:
        return 1.0
    if not expected_words or not actual_words:
        return 0.0
    matcher = difflib.SequenceMatcher(a=expected_words, b=actual_words)
    return float(matcher.ratio())


def verify_consent_audio(
    audio_path: Path,
    *,
    client: Any,
    language_code: str = "en-GB",
    model: str = "gemini-3.5-transcribe",
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> ConsentCheckResult:
    """Transcribe `audio_path` with `gemini-3.5-transcribe` and verify consent wording."""
    if not audio_path.exists():
        msg = f"Consent audio file not found: {audio_path}"
        raise FileNotFoundError(msg)

    expected_phrase = get_consent_phrase(language_code)
    audio_b64 = base64.b64encode(audio_path.read_bytes()).decode("utf-8")

    bcp47_hint = "en-GB" if language_code == "en" else language_code
    interaction = client.interactions.create(
        model=model,
        input=[
            {
                "type": "audio",
                "data": audio_b64,
                "mime_type": "audio/wav",
            }
        ],
        generation_config={
            "transcription_config": {
                "language_codes": [bcp47_hint],
            }
        },
    )

    transcript = (getattr(interaction, "output_text", None) or "").strip()
    similarity = compute_phrase_similarity(expected_phrase, transcript)

    return ConsentCheckResult(
        passed=similarity >= threshold,
        language_code=language_code,
        expected_phrase=expected_phrase,
        transcript=transcript,
        similarity=round(similarity, 4),
        audio_path=audio_path,
    )
