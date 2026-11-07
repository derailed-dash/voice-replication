"""Configuration management for the Personal Voice Replication & TTS Manager.

Loads settings from `.env` or environment variables using `pydantic-settings`,
providing typed defaults for your Google Cloud project, the regional Coldline
GCS backup bucket, and Gemini 3.8 TTS models.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings backed by environment variables and `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("*", mode="before")
    @classmethod
    def _strip_surrounding_quotes(cls, value: Any) -> Any:
        if isinstance(value, str):
            stripped = value.strip()
            if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {'"', "'"}:
                return stripped[1:-1]
        return value

    gemini_api_key: str = Field(
        default="",
        description="Gemini Developer API key created in your target GCP project.",
    )
    gcp_project_id: str = Field(
        default="my-gcp-project",
        description="Google Cloud project ID for GCS storage and security checks.",
    )
    gcs_bucket_name: str = Field(
        default="my-voice-replication",
        description="Regional GCS bucket name for voice audio and registry backups.",
    )
    gcs_location: str = Field(
        default="europe-west2",
        description="GCS bucket region (default London europe-west2).",
    )
    gcs_default_storage_class: str = Field(
        default="COLDLINE",
        description="Default GCS storage class for rare-read master WAV files.",
    )
    default_tts_model: str = Field(
        default="gemini-3.8-flash-tts",
        description="Primary expressive Gemini TTS model.",
    )
    fast_tts_model: str = Field(
        default="gemini-3.8-flash-lite-tts",
        description="High-throughput lightweight Gemini TTS model.",
    )
    transcribe_model: str = Field(
        default="gemini-3.5-transcribe",
        description="Speech-to-text model used for consent phrase pre-flight verification.",
    )
    default_voice_alias: str = Field(
        default="primary",
        description="Default local alias for personal voice replication.",
    )
    data_dir: Path = Field(
        default=Path("data"),
        description="Local git-ignored directory for voices.json and normalised WAV files.",
    )
    output_dir: Path = Field(
        default=Path("output"),
        description="Default directory for synthesised speech outputs.",
    )

    @property
    def catalogue_path(self) -> Path:
        """Return the local filesystem path for the `voices.json` registry."""
        return self.data_dir / "voices.json"

    def audio_dir_for_alias(self, alias: str) -> Path:
        """Return the local directory storing `source.wav` and `consent.wav` for `alias`."""
        return self.data_dir / "audio" / alias


def get_settings() -> Settings:
    """Instantiate and return the active `Settings` object."""
    return Settings()
