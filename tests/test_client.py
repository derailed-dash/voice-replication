"""Unit tests for the Gemini Voices & TTS Interactions API wrapper (`client.py`)."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from voice_replication.client import VoiceReplicationClient
from voice_replication.models import (
    DialogueScript,
    DialogueTurn,
    StorageMode,
    VoiceCatalogue,
    VoiceRecord,
    VoiceType,
)


@dataclass
class _FakeAudioOutput:
    data: str
    mime_type: str = "audio/wav"


@dataclass
class _FakeVoiceResponse:
    id: str | None = None
    key: str | None = None
    display_name: str | None = None
    type: str = "replicated"
    sample_audio: _FakeAudioOutput | None = None


@dataclass
class _FakeVoiceListResponse:
    voices: list[_FakeVoiceResponse] = field(default_factory=list)


@dataclass
class _FakeInteractionResponse:
    output_audio: _FakeAudioOutput | None = None


class _FakeVoicesResource:
    def __init__(self) -> None:
        self.created_calls: list[dict[str, Any]] = []
        self.deleted_ids: list[str] = []
        self.remote_voices: list[_FakeVoiceResponse] = [
            _FakeVoiceResponse(
                id="voice_existing_1",
                display_name="Dazbo Primary",
                type="replicated",
            )
        ]

    def create(self, **kwargs: Any) -> _FakeVoiceResponse:
        self.created_calls.append(kwargs)
        store = kwargs.get("store", True)
        voice_cfg = kwargs.get("voice", {})
        vtype = voice_cfg.get("type", "replicated")
        display_name = voice_cfg.get("display_name")
        if not store:
            return _FakeVoiceResponse(
                id=None,
                key="voicekey_stateless_999",
                display_name=display_name,
                type=vtype,
            )
        sample_b64 = base64.b64encode(b"RIFF_PREVIEW_WAV").decode("utf-8")
        return _FakeVoiceResponse(
            id=f"voice_{vtype}_123",
            key=None,
            display_name=display_name,
            type=vtype,
            sample_audio=_FakeAudioOutput(data=sample_b64) if vtype == "prompted" else None,
        )

    def list(self, **kwargs: Any) -> _FakeVoiceListResponse:
        return _FakeVoiceListResponse(voices=self.remote_voices)

    def get(self, *, id: str) -> _FakeVoiceResponse:
        return _FakeVoiceResponse(id=id, display_name="Dazbo Primary", type="replicated")

    def delete(self, *, id: str) -> None:
        self.deleted_ids.append(id)


class _FakeInteractionsResource:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> _FakeInteractionResponse:
        self.calls.append(kwargs)
        audio_b64 = base64.b64encode(b"RIFF_SYNTHESISED_WAV_BYTES").decode("utf-8")
        return _FakeInteractionResponse(output_audio=_FakeAudioOutput(data=audio_b64))


class _FakeGenAIClient:
    def __init__(self) -> None:
        self.voices = _FakeVoicesResource()
        self.interactions = _FakeInteractionsResource()


class TestVoiceReplicationClientCRUD:
    """Verify stateful/stateless voice replication, Voice Design, and remote CRUD."""

    def test_default_client_uses_v1beta_api_version(self, monkeypatch: Any) -> None:
        captured_kwargs: dict[str, Any] = {}

        def _fake_genai_client(**kwargs: Any) -> _FakeGenAIClient:
            captured_kwargs.update(kwargs)
            return _FakeGenAIClient()

        monkeypatch.setattr("voice_replication.client.genai.Client", _fake_genai_client)
        VoiceReplicationClient(api_key="test-key")
        assert captured_kwargs["api_key"] == "test-key"
        assert captured_kwargs["http_options"] == {"api_version": "v1beta"}

    def test_create_stateful_replicated_voice(
        self, sample_reference_wav: Path, sample_consent_wav: Path
    ) -> None:
        fake_genai = _FakeGenAIClient()
        vr_client = VoiceReplicationClient(client=fake_genai)

        record = vr_client.create_replicated_voice(
            alias="dazbo",
            display_name="Dazbo Primary",
            source_wav_path=sample_reference_wav,
            consent_wav_path=sample_consent_wav,
            store=True,
            default_style="warm and conversational",
        )
        assert record.alias == "dazbo"
        assert record.storage_mode == StorageMode.STATEFUL
        assert record.voice_id == "voice_replicated_123"
        assert record.effective_token == "voice_replicated_123"
        assert len(fake_genai.voices.created_calls) == 1
        call = fake_genai.voices.created_calls[0]
        assert call["store"] is True
        assert call["voice"]["type"] == "replicated"
        assert call["voice"]["display_name"] == "Dazbo Primary"

    def test_create_stateless_replicated_voice(
        self, sample_reference_wav: Path, sample_consent_wav: Path
    ) -> None:
        fake_genai = _FakeGenAIClient()
        vr_client = VoiceReplicationClient(client=fake_genai)

        record = vr_client.create_replicated_voice(
            alias="dazbo-stateless",
            display_name="Dazbo Stateless",
            source_wav_path=sample_reference_wav,
            consent_wav_path=sample_consent_wav,
            store=False,
        )
        assert record.storage_mode == StorageMode.STATELESS
        assert record.voice_key == "voicekey_stateless_999"
        assert record.effective_token == "voicekey_stateless_999"

    def test_create_designed_voice_with_preview(self, tmp_path: Path) -> None:
        fake_genai = _FakeGenAIClient()
        vr_client = VoiceReplicationClient(client=fake_genai)
        preview_path = tmp_path / "preview.wav"

        record = vr_client.create_designed_voice(
            alias="cohost",
            display_name="Podcast Co-Host",
            prompt="An inquisitive British engineer in her 30s.",
            gender="female",
            language_code="en-GB",
            preview_output_path=preview_path,
        )
        assert record.voice_type == VoiceType.PROMPTED
        assert record.voice_id == "voice_prompted_123"
        assert preview_path.exists()
        assert preview_path.read_bytes() == b"RIFF_PREVIEW_WAV"

    def test_list_get_and_delete_remote_voices(self) -> None:
        fake_genai = _FakeGenAIClient()
        vr_client = VoiceReplicationClient(client=fake_genai)

        voices = vr_client.list_remote_voices()
        assert len(voices) == 1
        assert voices[0]["id"] == "voice_existing_1"

        detail = vr_client.get_remote_voice("voice_existing_1")
        assert detail["id"] == "voice_existing_1"

        vr_client.delete_remote_voice("voice_existing_1")
        assert fake_genai.voices.deleted_ids == ["voice_existing_1"]


class TestVoiceReplicationClientSynthesis:
    """Verify single-speaker and multi-speaker TTS synthesis calls."""

    def test_synthesise_single_speaker_writes_wav(self, tmp_path: Path) -> None:
        fake_genai = _FakeGenAIClient()
        vr_client = VoiceReplicationClient(client=fake_genai)
        out_wav = tmp_path / "speech.wav"

        vr_client.synthesise_single_speaker(
            text="Hello from my replicated voice!",
            voice_id_or_key="voice_replicated_123",
            output_wav_path=out_wav,
            style="cheerful and brisk",
            model="gemini-3.8-flash-tts",
        )
        assert out_wav.exists()
        assert out_wav.read_bytes() == b"RIFF_SYNTHESISED_WAV_BYTES"
        call = fake_genai.interactions.calls[0]
        assert call["model"] == "gemini-3.8-flash-tts"
        assert call["generation_config"]["speech_config"] == [{"voice": "voice_replicated_123"}]
        content_item = call["input"][0]["content"][0]
        assert content_item["text"] == "Hello from my replicated voice!"
        assert content_item["annotations"] == [
            {"type": "speech_metadata", "style": "cheerful and brisk"}
        ]

    def test_synthesise_dialogue_resolves_catalogue_aliases(self, tmp_path: Path) -> None:
        fake_genai = _FakeGenAIClient()
        vr_client = VoiceReplicationClient(client=fake_genai)

        catalogue = VoiceCatalogue()
        catalogue.upsert(
            VoiceRecord(
                alias="dazbo",
                display_name="Dazbo Primary",
                voice_type=VoiceType.REPLICATED,
                storage_mode=StorageMode.STATEFUL,
                voice_id="voice_dazbo_777",
            )
        )
        script = DialogueScript(
            model="gemini-3.8-flash-tts",
            speakers={"Dazbo": "dazbo", "Guest": "Kore"},
            turns=[
                DialogueTurn(speaker="Dazbo", text="Hi Guest!", style="warm"),
                DialogueTurn(speaker="Guest", text="Hi Dazbo!", style="calm"),
            ],
        )
        out_wav = tmp_path / "dialogue.wav"
        vr_client.synthesise_dialogue(
            script=script,
            output_wav_path=out_wav,
            catalogue=catalogue,
        )
        assert out_wav.exists()
        call = fake_genai.interactions.calls[0]
        assert call["generation_config"]["speech_config"] == {
            "speakers": [
                {"speaker": "Dazbo", "voice": "voice_dazbo_777"},
                {"speaker": "Guest", "voice": "Kore"},
            ]
        }
        assert len(call["input"][0]["content"]) == 2
