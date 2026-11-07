"""Unit and integration tests for `audio.py` using real `ffmpeg` and `ffprobe`."""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.conftest import generate_sine_wav

from voice_replication.audio import (
    AudioValidationError,
    export_mp3,
    inspect_audio,
    normalise_audio,
    validate_reference_duration,
)


class TestInspectAudio:
    """Verify `ffprobe` stream inspection on real WAV files."""

    def test_inspect_valid_24k_mono_wav(self, sample_reference_wav: Path) -> None:
        stats = inspect_audio(sample_reference_wav)
        assert stats.sample_rate == 24000
        assert stats.channels == 1
        assert stats.codec_name == "pcm_s16le"
        assert stats.duration_seconds == pytest.approx(12.0, abs=0.2)
        assert stats.is_24k_mono_pcm is True
        assert stats.is_valid_reference_duration is True

    def test_inspect_missing_file_raises_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            inspect_audio(tmp_path / "does_not_exist.wav")


class TestNormaliseAudio:
    """Verify `ffmpeg` resampling to 24kHz mono 16-bit PCM WAV and trimming."""

    def test_normalise_48k_stereo_to_24k_mono_wav(self, tmp_path: Path) -> None:
        raw_stereo = generate_sine_wav(
            tmp_path / "raw_stereo_48k.wav",
            duration_seconds=14.0,
            sample_rate=48000,
            channels=2,
        )
        raw_stats = inspect_audio(raw_stereo)
        assert raw_stats.is_24k_mono_pcm is False

        out_wav = tmp_path / "normalised" / "source.wav"
        stats = normalise_audio(raw_stereo, out_wav)
        assert out_wav.exists()
        assert stats.sample_rate == 24000
        assert stats.channels == 1
        assert stats.codec_name == "pcm_s16le"
        assert stats.is_24k_mono_pcm is True
        assert stats.duration_seconds == pytest.approx(14.0, abs=0.2)

    def test_normalise_with_trim_start_and_end(self, tmp_path: Path) -> None:
        long_raw = generate_sine_wav(
            tmp_path / "long_clip.wav",
            duration_seconds=36.0,
            sample_rate=44100,
            channels=1,
        )
        out_wav = tmp_path / "trimmed_source.wav"
        stats = normalise_audio(long_raw, out_wav, trim_start=2.0, trim_end=22.0)
        assert stats.is_24k_mono_pcm is True
        assert stats.duration_seconds == pytest.approx(20.0, abs=0.3)
        assert stats.is_valid_reference_duration is True


class TestValidateReferenceDuration:
    """Verify 10.0-30.0s duration enforcement for reference audio clips."""

    def test_short_clip_raises_audio_validation_error(self, tmp_path: Path) -> None:
        short_wav = generate_sine_wav(tmp_path / "short.wav", duration_seconds=4.0)
        stats = inspect_audio(short_wav)
        with pytest.raises(AudioValidationError, match=r"between 10\.0s and 30\.0s"):
            validate_reference_duration(stats)

    def test_valid_clip_passes_duration_validation(self, sample_reference_wav: Path) -> None:
        stats = inspect_audio(sample_reference_wav)
        validate_reference_duration(stats)


class TestExportMp3:
    """Verify MP3 conversion from WAV via `ffmpeg`."""

    def test_export_wav_to_mp3(self, sample_consent_wav: Path, tmp_path: Path) -> None:
        mp3_path = tmp_path / "out.mp3"
        result_path = export_mp3(sample_consent_wav, mp3_path)
        assert result_path == mp3_path
        assert mp3_path.exists()
        assert mp3_path.stat().st_size > 1000
