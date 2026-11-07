"""Personal Voice Replication & Expressive TTS Manager (`voice_replication`).

Provides audio preprocessing (`ffmpeg`/`ffprobe` 24kHz mono 16-bit PCM WAV),
mandatory consent verification (`gemini-3.5-transcribe`), stateful/stateless
voice replication and Voice Design (`client.voices`), single- and multi-speaker
speech synthesis (`gemini-3.8-flash-tts`), and Google Cloud Storage backup.
"""

from __future__ import annotations

from voice_replication.audio import (
    AudioValidationError,
    export_mp3,
    inspect_audio,
    normalise_audio,
    validate_reference_duration,
)
from voice_replication.client import (
    VoiceReplicationClient,
    build_dialogue_payload,
    build_single_speaker_payload,
)
from voice_replication.config import Settings, get_settings
from voice_replication.consent import (
    DEFAULT_ENGLISH_CONSENT_PHRASE,
    compute_phrase_similarity,
    get_consent_phrase,
    verify_consent_audio,
)
from voice_replication.models import (
    AudioStats,
    ConsentCheckResult,
    DialogueScript,
    DialogueTurn,
    StorageMode,
    VoiceCatalogue,
    VoiceRecord,
    VoiceType,
)
from voice_replication.storage import (
    GCSBackupManager,
    generate_bucket_architect_commands,
    load_catalogue,
    save_catalogue,
)

__version__ = "0.1.0"

__all__ = [
    "DEFAULT_ENGLISH_CONSENT_PHRASE",
    "AudioStats",
    "AudioValidationError",
    "ConsentCheckResult",
    "DialogueScript",
    "DialogueTurn",
    "GCSBackupManager",
    "Settings",
    "StorageMode",
    "VoiceCatalogue",
    "VoiceRecord",
    "VoiceReplicationClient",
    "VoiceType",
    "__version__",
    "build_dialogue_payload",
    "build_single_speaker_payload",
    "compute_phrase_similarity",
    "export_mp3",
    "generate_bucket_architect_commands",
    "get_consent_phrase",
    "get_settings",
    "inspect_audio",
    "load_catalogue",
    "normalise_audio",
    "save_catalogue",
    "validate_reference_duration",
    "verify_consent_audio",
]
