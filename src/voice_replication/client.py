"""Gemini Voices and TTS Interactions API client wrapper (`client.py`).

Wraps `google.genai.Client` (`client.voices` and `client.interactions.create`)
to provide stateful (`store=True`) and stateless (`store=False`) Voice
Replication, natural-language Voice Design (`type='prompted'`), remote voice
catalogue inspection, and single/multi-speaker TTS synthesis.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from google import genai

from voice_replication.models import (
    DialogueScript,
    StorageMode,
    VoiceCatalogue,
    VoiceRecord,
    VoiceType,
)


def build_single_speaker_payload(
    text: str,
    voice_id_or_key: str,
    *,
    model: str = "gemini-3.8-flash-tts",
    style: str | None = None,
) -> dict[str, Any]:
    """Construct the Interactions API request dictionary for single-speaker TTS."""
    content_item: dict[str, Any] = {"type": "text", "text": text}
    if style:
        content_item["annotations"] = [{"type": "speech_metadata", "style": style}]

    return {
        "model": model,
        "input": [{"type": "user_input", "content": [content_item]}],
        "response_format": {"type": "audio"},
        "generation_config": {
            "speech_config": [{"voice": voice_id_or_key}],
        },
    }


def build_dialogue_payload(
    script: DialogueScript,
    *,
    catalogue: VoiceCatalogue | None = None,
) -> dict[str, Any]:
    """Construct the Interactions API request dictionary for multi-speaker dialogue TTS."""
    speaker_configs: list[dict[str, str]] = []
    for speaker_name, alias_or_id in script.speakers.items():
        resolved_voice = alias_or_id
        if catalogue is not None:
            record = catalogue.get(alias_or_id)
            if record is not None:
                resolved_voice = record.effective_token
        speaker_configs.append({"speaker": speaker_name, "voice": resolved_voice})

    content_items: list[dict[str, Any]] = []
    for turn in script.turns:
        annotation: dict[str, Any] = {
            "type": "speech_metadata",
            "speaker": turn.speaker,
        }
        if turn.style:
            annotation["style"] = turn.style
        content_items.append(
            {
                "type": "text",
                "text": turn.text,
                "annotations": [annotation],
            }
        )

    return {
        "model": script.model,
        "input": [{"type": "user_input", "content": content_items}],
        "response_format": {"type": "audio"},
        "generation_config": {
            "speech_config": {
                "speakers": speaker_configs,
            }
        },
    }


class VoiceReplicationClient:
    """High-level wrapper around `google.genai.Client` for Voices and TTS."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        client: Any | None = None,
    ) -> None:
        self.client: Any
        if client is not None:
            self.client = client
        elif api_key:
            self.client = genai.Client(api_key=api_key)
        else:
            self.client = genai.Client()

    def create_replicated_voice(
        self,
        *,
        alias: str,
        display_name: str,
        source_wav_path: Path,
        consent_wav_path: Path,
        store: bool = True,
        model: str = "gemini-3.8-flash-tts",
        default_style: str | None = None,
        language_code: str = "en-GB",
    ) -> VoiceRecord:
        """Create a stateful (`store=True`) or stateless (`store=False`) replicated voice."""
        source_b64 = base64.b64encode(source_wav_path.read_bytes()).decode("utf-8")
        consent_b64 = base64.b64encode(consent_wav_path.read_bytes()).decode("utf-8")

        voice_payload: dict[str, Any] = {
            "model": model,
            "type": "replicated",
            "replicated": {
                "source_audio": {"mime_type": "audio/wav", "data": source_b64},
                "consent_audio": {"mime_type": "audio/wav", "data": consent_b64},
            },
        }
        if store:
            voice_payload["display_name"] = display_name

        response = self.client.voices.create(store=store, voice=voice_payload)
        voice_id = getattr(response, "id", None)
        voice_key = getattr(response, "key", None)

        return VoiceRecord(
            alias=alias,
            display_name=display_name,
            voice_type=VoiceType.REPLICATED,
            storage_mode=StorageMode.STATEFUL if store else StorageMode.STATELESS,
            voice_id=voice_id,
            voice_key=voice_key,
            model=model,
            default_style=default_style,
            language_code=language_code,
            source_audio_path=str(source_wav_path),
            consent_audio_path=str(consent_wav_path),
        )

    def create_designed_voice(
        self,
        *,
        alias: str,
        display_name: str,
        prompt: str,
        gender: str = "female",
        language_code: str = "en-GB",
        model: str = "gemini-3.8-flash-tts",
        default_style: str | None = None,
        preview_output_path: Path | None = None,
    ) -> VoiceRecord:
        """Create a persistent Voice Design (`type='prompted'`) persona."""
        response = self.client.voices.create(
            store=True,
            voice={
                "model": model,
                "type": "prompted",
                "display_name": display_name,
                "gender": gender,
                "language_code": language_code,
                "prompted": {"input": prompt},
            },
        )
        sample_audio = getattr(response, "sample_audio", None)
        if preview_output_path and sample_audio and getattr(sample_audio, "data", None):
            preview_output_path.parent.mkdir(parents=True, exist_ok=True)
            preview_output_path.write_bytes(base64.b64decode(sample_audio.data))

        return VoiceRecord(
            alias=alias,
            display_name=display_name,
            voice_type=VoiceType.PROMPTED,
            storage_mode=StorageMode.STATEFUL,
            voice_id=getattr(response, "id", None),
            model=model,
            default_style=default_style,
            prompt=prompt,
            language_code=language_code,
        )

    def list_remote_voices(
        self,
        *,
        types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """List stored custom voices in the Gemini API project."""
        filter_types = types or ["replicated", "prompted"]
        response = self.client.voices.list(type_=filter_types)
        voices = getattr(response, "voices", None) or []
        return [
            {
                "id": getattr(v, "id", None),
                "display_name": getattr(v, "display_name", None),
                "type": getattr(v, "type", None),
            }
            for v in voices
        ]

    def get_remote_voice(self, voice_id: str) -> dict[str, Any]:
        """Fetch details of a stored voice by `voice_id`."""
        v = self.client.voices.get(id=voice_id)
        return {
            "id": getattr(v, "id", voice_id),
            "display_name": getattr(v, "display_name", None),
            "type": getattr(v, "type", None),
        }

    def delete_remote_voice(self, voice_id: str) -> None:
        """Delete a stored voice from the Gemini API project."""
        self.client.voices.delete(id=voice_id)

    def synthesise_single_speaker(
        self,
        *,
        text: str,
        voice_id_or_key: str,
        output_wav_path: Path,
        style: str | None = None,
        model: str = "gemini-3.8-flash-tts",
    ) -> Path:
        """Synthesise single-speaker speech and write the resulting WAV file."""
        payload = build_single_speaker_payload(
            text=text,
            voice_id_or_key=voice_id_or_key,
            model=model,
            style=style,
        )
        interaction = self.client.interactions.create(**payload)
        return self._write_interaction_audio(interaction, output_wav_path)

    def synthesise_dialogue(
        self,
        *,
        script: DialogueScript,
        output_wav_path: Path,
        catalogue: VoiceCatalogue | None = None,
    ) -> Path:
        """Synthesise a multi-speaker `DialogueScript` and write the resulting WAV file."""
        payload = build_dialogue_payload(script, catalogue=catalogue)
        interaction = self.client.interactions.create(**payload)
        return self._write_interaction_audio(interaction, output_wav_path)

    @staticmethod
    def _write_interaction_audio(interaction: Any, output_wav_path: Path) -> Path:
        output_audio = getattr(interaction, "output_audio", None)
        audio_b64 = getattr(output_audio, "data", None) if output_audio else None
        if not audio_b64:
            msg = "Gemini TTS interaction returned no output_audio data."
            raise RuntimeError(msg)

        output_wav_path.parent.mkdir(parents=True, exist_ok=True)
        output_wav_path.write_bytes(base64.b64decode(audio_b64))
        return output_wav_path
