"""Shared pytest fixtures for the `voice-replication` test suite.

Provides deterministic synthetic WAV file generators and temporary workspace
paths so unit and integration tests run offline at $0 cost.
"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

import pytest


def generate_sine_wav(
    path: Path,
    *,
    duration_seconds: float = 12.0,
    sample_rate: int = 24000,
    channels: int = 1,
    frequency_hz: float = 440.0,
) -> Path:
    """Write a deterministic 16-bit PCM sine-wave WAV file to `path`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    total_frames = int(duration_seconds * sample_rate)
    amplitude = 12000  # Safe 16-bit signed integer amplitude

    # Pre-compute one cycle of samples for fast generation
    frames = bytearray()
    for i in range(total_frames):
        sample = int(amplitude * math.sin(2.0 * math.pi * frequency_hz * (i / sample_rate)))
        packed = struct.pack("<h", sample)
        frames.extend(packed * channels)

    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)  # 16-bit PCM
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(bytes(frames))

    return path


@pytest.fixture
def sample_reference_wav(tmp_path: Path) -> Path:
    """Create a valid 12-second 24kHz mono 16-bit WAV file for reference audio tests."""
    return generate_sine_wav(
        tmp_path / "reference.wav",
        duration_seconds=12.0,
        sample_rate=24000,
        channels=1,
    )


@pytest.fixture
def sample_consent_wav(tmp_path: Path) -> Path:
    """Create a valid 5-second 24kHz mono 16-bit WAV file for consent audio tests."""
    return generate_sine_wav(
        tmp_path / "consent.wav",
        duration_seconds=5.0,
        sample_rate=24000,
        channels=1,
    )
