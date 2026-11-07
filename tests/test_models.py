"""Unit tests for configuration settings and domain models (`config.py`, `models.py`)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from voice_replication.config import Settings
from voice_replication.models import (
    AudioStats,
    DialogueScript,
    DialogueTurn,
    StorageMode,
    VoiceCatalogue,
    VoiceRecord,
    VoiceType,
)


class TestSettings:
    """Verify environment configuration loading and derived path helpers."""

    def test_default_settings_values(self, tmp_path: Path) -> None:
        settings = Settings(
            _env_file=None,  # type: ignore[call-arg]
            gemini_api_key="test-key-123",
            data_dir=tmp_path / "data",
            output_dir=tmp_path / "output",
        )
        assert settings.gcp_project_id == "my-gcp-project"
        assert settings.gcs_bucket_name == "my-voice-replication"
        assert settings.gcs_location == "europe-west2"
        assert settings.gcs_default_storage_class == "COLDLINE"
        assert settings.default_tts_model == "gemini-3.8-flash-tts"
        assert settings.fast_tts_model == "gemini-3.8-flash-lite-tts"
        assert settings.transcribe_model == "gemini-3.5-transcribe"
        assert settings.default_voice_alias == "primary"
        assert settings.catalogue_path == tmp_path / "data" / "voices.json"
        assert settings.audio_dir_for_alias("dazbo") == tmp_path / "data" / "audio" / "dazbo"

    def test_strips_surrounding_quotes_from_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", '"AQ.quoted-key-value"')
        monkeypatch.setenv("GCP_PROJECT_ID", "'quoted-project'")
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        assert settings.gemini_api_key == "AQ.quoted-key-value"
        assert settings.gcp_project_id == "quoted-project"


class TestAudioStats:
    """Verify audio format and duration validation properties."""

    def test_valid_24k_mono_pcm_reference_stats(self) -> None:
        stats = AudioStats(
            path=Path("source.wav"),
            sample_rate=24000,
            channels=1,
            codec_name="pcm_s16le",
            duration_seconds=18.5,
            size_bytes=888000,
        )
        assert stats.is_24k_mono_pcm is True
        assert stats.is_valid_reference_duration is True

    def test_invalid_format_and_duration_stats(self) -> None:
        stats = AudioStats(
            path=Path("raw.mp3"),
            sample_rate=44100,
            channels=2,
            codec_name="mp3",
            duration_seconds=6.2,
            size_bytes=120000,
        )
        assert stats.is_24k_mono_pcm is False
        assert stats.is_valid_reference_duration is False


class TestVoiceRecordAndCatalogue:
    """Verify voice lifecycle metadata, TTL calculations, and catalogue CRUD."""

    def test_stateful_replicated_voice_computes_one_year_ttl(self) -> None:
        created = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
        record = VoiceRecord(
            alias="dazbo",
            display_name="Dazbo Primary",
            voice_type=VoiceType.REPLICATED,
            storage_mode=StorageMode.STATEFUL,
            voice_id="voice_abc123",
            model="gemini-3.8-flash-tts",
            default_style="warm and conversational",
            created_at=created,
        )
        assert record.expires_at == created + timedelta(days=365)
        assert record.effective_token == "voice_abc123"
        assert record.is_expired(now=created + timedelta(days=100)) is False
        assert record.is_expired(now=created + timedelta(days=366)) is True
        assert record.days_until_expiry(now=created + timedelta(days=300)) == 65

    def test_stateless_replicated_voice_computes_seven_day_ttl(self) -> None:
        created = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
        record = VoiceRecord(
            alias="dazbo-temp",
            display_name="Dazbo Stateless",
            voice_type=VoiceType.REPLICATED,
            storage_mode=StorageMode.STATELESS,
            voice_key="voicekey_xyz789",
            model="gemini-3.8-flash-tts",
            created_at=created,
        )
        assert record.expires_at == created + timedelta(days=7)
        assert record.effective_token == "voicekey_xyz789"
        assert record.is_expired(now=created + timedelta(days=8)) is True

    def test_missing_voice_id_and_key_raises_error(self) -> None:
        with pytest.raises(ValueError, match="requires either voice_id or voice_key"):
            VoiceRecord(
                alias="broken",
                display_name="Broken Voice",
                voice_type=VoiceType.REPLICATED,
                storage_mode=StorageMode.STATEFUL,
            )

    def test_catalogue_crud_operations(self) -> None:
        catalogue = VoiceCatalogue()
        record = VoiceRecord(
            alias="dazbo",
            display_name="Dazbo Primary",
            voice_type=VoiceType.REPLICATED,
            storage_mode=StorageMode.STATEFUL,
            voice_id="voice_abc123",
        )
        catalogue.upsert(record)
        assert catalogue.get("dazbo") == record
        assert len(catalogue.list_voices()) == 1
        assert len(catalogue.list_voices(voice_type=VoiceType.PROMPTED)) == 0
        assert catalogue.remove("dazbo") is True
        assert catalogue.get("dazbo") is None
        assert catalogue.remove("dazbo") is False


class TestDialogueScript:
    """Verify multi-speaker dialogue YAML parsing and speaker validation."""

    def test_parse_valid_dialogue_yaml(self) -> None:
        yaml_text = """
model: gemini-3.8-flash-tts
speakers:
  Dazbo: dazbo
  CoHost: Kore
turns:
  - speaker: Dazbo
    text: "Welcome to the show! [laugh] Great to be here."
    style: "warm and enthusiastic"
  - speaker: CoHost
    text: "Thanks Dazbo, let's dive into Gemini 3.8 TTS."
    style: "calm and inquisitive"
"""
        script = DialogueScript.from_yaml_str(yaml_text)
        assert script.model == "gemini-3.8-flash-tts"
        assert script.speakers == {"Dazbo": "dazbo", "CoHost": "Kore"}
        assert len(script.turns) == 2
        assert script.turns[0].speaker == "Dazbo"

    def test_unknown_turn_speaker_raises_validation_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown speaker 'Ghost'"):
            DialogueScript(
                speakers={"Dazbo": "dazbo", "CoHost": "Kore"},
                turns=[DialogueTurn(speaker="Ghost", text="Who am I?")],
            )
