"""Domain models and schemas for Voice Replication, Audio Inspection, and Dialogue TTS.

Defines Pydantic models for the local/GCS `voices.json` catalogue, 1-year stateful
(`store=True`) and 7-day stateless (`store=False`) TTL tracking, audio stream
inspection statistics, and multi-speaker YAML dialogue scripts.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, Field, model_validator

RECOMMENDED_SAMPLE_RATE_HZ = 24000
RECOMMENDED_CHANNELS = 1
RECOMMENDED_CODEC = "pcm_s16le"
MIN_REFERENCE_DURATION_SECONDS = 10.0
MAX_REFERENCE_DURATION_SECONDS = 30.0
STATEFUL_TTL_DAYS = 365
STATELESS_TTL_DAYS = 7


class VoiceType(StrEnum):
    """Supported Gemini custom voice types."""

    REPLICATED = "replicated"
    PROMPTED = "prompted"


class StorageMode(StrEnum):
    """Storage persistence mode for `client.voices.create`."""

    STATEFUL = "stateful"
    STATELESS = "stateless"


class AudioStats(BaseModel):
    """Technical metadata inspected from an audio file via `ffprobe`."""

    path: Path
    sample_rate: int
    channels: int
    codec_name: str
    duration_seconds: float
    size_bytes: int

    @property
    def is_24k_mono_pcm(self) -> bool:
        """Return True if the file matches the recommended 24kHz mono 16-bit PCM WAV spec."""
        return (
            self.sample_rate == RECOMMENDED_SAMPLE_RATE_HZ
            and self.channels == RECOMMENDED_CHANNELS
            and self.codec_name == RECOMMENDED_CODEC
        )

    @property
    def is_valid_reference_duration(self) -> bool:
        """Return True if duration falls within the 10-30 second reference audio window."""
        return (
            MIN_REFERENCE_DURATION_SECONDS
            <= self.duration_seconds
            <= MAX_REFERENCE_DURATION_SECONDS
        )


class ConsentCheckResult(BaseModel):
    """Structured result of verifying a speaker's consent recording via STT."""

    passed: bool
    language_code: str
    expected_phrase: str
    transcript: str
    similarity: float
    audio_path: Path


class VoiceRecord(BaseModel):
    """Metadata record for a replicated or designed custom voice."""

    alias: str = Field(..., min_length=1, description="Human-friendly local voice alias.")
    display_name: str = Field(..., min_length=1, description="Display name passed to Gemini API.")
    voice_type: VoiceType = Field(default=VoiceType.REPLICATED)
    storage_mode: StorageMode = Field(default=StorageMode.STATEFUL)
    voice_id: str | None = Field(
        default=None,
        description="Server-side voice ID (`voice_...`) when `store=True`.",
    )
    voice_key: str | None = Field(
        default=None,
        description="Client-managed encrypted key (`voicekey_...`) when `store=False`.",
    )
    model: str = Field(default="gemini-3.8-flash-tts")
    default_style: str | None = Field(
        default=None,
        description="Optional default `speech_metadata` style instruction.",
    )
    prompt: str | None = Field(
        default=None,
        description="Natural-language persona description when `voice_type == 'prompted'`.",
    )
    language_code: str = Field(default="en-GB")
    source_audio_path: str | None = Field(default=None)
    consent_audio_path: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = Field(default=None)

    @model_validator(mode="after")
    def _validate_identifiers_and_ttl(self) -> Self:
        if not self.voice_id and not self.voice_key:
            msg = f"VoiceRecord '{self.alias}' requires either voice_id or voice_key."
            raise ValueError(msg)

        if self.expires_at is None:
            ttl_days = (
                STATELESS_TTL_DAYS
                if self.storage_mode == StorageMode.STATELESS
                else STATEFUL_TTL_DAYS
            )
            self.expires_at = self.created_at + timedelta(days=ttl_days)
        return self

    @property
    def effective_token(self) -> str:
        """Return the identifier (`voice_...` or `voicekey_...`) used in `speech_config`."""
        if self.voice_id:
            return self.voice_id
        if self.voice_key:
            return self.voice_key
        msg = f"VoiceRecord '{self.alias}' has no voice_id or voice_key."
        raise ValueError(msg)

    def is_expired(self, *, now: datetime | None = None) -> bool:
        """Return True if the voice has passed its retention TTL."""
        reference = now or datetime.now(UTC)
        if self.expires_at is None:
            return False
        return reference >= self.expires_at

    def days_until_expiry(self, *, now: datetime | None = None) -> int:
        """Return integer days remaining before TTL expiry (negative if expired)."""
        reference = now or datetime.now(UTC)
        if self.expires_at is None:
            return STATEFUL_TTL_DAYS
        delta = self.expires_at - reference
        return delta.days


class VoiceCatalogue(BaseModel):
    """Persistent registry of custom voices stored in `data/voices.json` and GCS."""

    version: int = 1
    project_id: str = "my-gcp-project"
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    voices: dict[str, VoiceRecord] = Field(default_factory=dict)

    def upsert(self, record: VoiceRecord) -> None:
        """Insert or update a `VoiceRecord` by its alias."""
        self.voices[record.alias] = record
        self.updated_at = datetime.now(UTC)

    def get(self, alias: str) -> VoiceRecord | None:
        """Retrieve a `VoiceRecord` by alias, or return None if not found."""
        return self.voices.get(alias)

    def remove(self, alias: str) -> bool:
        """Remove a `VoiceRecord` by alias. Return True if removed, False if absent."""
        if alias in self.voices:
            del self.voices[alias]
            self.updated_at = datetime.now(UTC)
            return True
        return False

    def list_voices(
        self,
        *,
        voice_type: VoiceType | None = None,
        include_expired: bool = True,
        now: datetime | None = None,
    ) -> list[VoiceRecord]:
        """Return sorted list of voice records matching optional filters."""
        records = list(self.voices.values())
        if voice_type is not None:
            records = [r for r in records if r.voice_type == voice_type]
        if not include_expired:
            records = [r for r in records if not r.is_expired(now=now)]
        return sorted(records, key=lambda r: r.alias)


class DialogueTurn(BaseModel):
    """A single speaker turn in a multi-speaker dialogue script."""

    speaker: str = Field(..., min_length=1, description="Logical speaker name in the script.")
    text: str = Field(..., min_length=1, description="Verbatim transcript for this turn.")
    style: str | None = Field(
        default=None,
        description="Optional turn-level `speech_metadata` style prompt.",
    )


class DialogueScript(BaseModel):
    """Multi-speaker dialogue definition linking speaker names to voice aliases/IDs."""

    model: str = Field(default="gemini-3.8-flash-tts")
    speakers: dict[str, str] = Field(
        ...,
        description="Mapping of script speaker name (e.g. 'Dazbo') to voice alias or ID.",
    )
    turns: list[DialogueTurn] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _validate_turn_speakers(self) -> Self:
        if not self.speakers:
            msg = "DialogueScript must define at least one speaker mapping."
            raise ValueError(msg)
        for turn in self.turns:
            if turn.speaker not in self.speakers:
                msg = (
                    f"Unknown speaker '{turn.speaker}' in turn. "
                    f"Defined speakers: {sorted(self.speakers.keys())}"
                )
                raise ValueError(msg)
        return self

    @classmethod
    def from_yaml_str(cls, raw_yaml: str) -> Self:
        """Parse and validate a `DialogueScript` from a YAML string."""
        data = yaml.safe_load(raw_yaml)
        if not isinstance(data, dict):
            msg = "Dialogue YAML must deserialize to a mapping/dictionary."
            raise ValueError(msg)
        return cls.model_validate(data)

    @classmethod
    def from_yaml_file(cls, path: Path) -> Self:
        """Load and validate a `DialogueScript` from a YAML file on disk."""
        return cls.from_yaml_str(path.read_text(encoding="utf-8"))
