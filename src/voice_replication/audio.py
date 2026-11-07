"""Audio inspection, 24kHz mono WAV normalisation, trimming, and MP3 export (`audio.py`).

Uses `ffprobe` and `ffmpeg` to inspect input recordings, resample any media
format (`.m4a`, `.mp3`, `.wav`, `.ogg`) to the Gemini Voice Replication
recommended format (**24kHz mono 16-bit PCM WAV**), enforce the 10.0-30.0
second reference duration window, and convert synthesised WAV output to MP3.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from voice_replication.models import (
    MAX_REFERENCE_DURATION_SECONDS,
    MIN_REFERENCE_DURATION_SECONDS,
    RECOMMENDED_CHANNELS,
    RECOMMENDED_CODEC,
    RECOMMENDED_SAMPLE_RATE_HZ,
    AudioStats,
)


class AudioValidationError(ValueError):
    """Raised when an audio file fails format or duration requirements."""


def _require_binary(binary_name: str) -> str:
    """Resolve `binary_name` on `$PATH` or raise `RuntimeError` with install hint."""
    resolved = shutil.which(binary_name)
    if not resolved:
        msg = (
            f"Required binary '{binary_name}' was not found on PATH. "
            "Hint: install ffmpeg via 'sudo apt install ffmpeg'."
        )
        raise RuntimeError(msg)
    return resolved


def inspect_audio(path: Path) -> AudioStats:
    """Inspect an audio file via `ffprobe` and return its `AudioStats`."""
    if not path.exists():
        msg = f"Audio file not found: {path}"
        raise FileNotFoundError(msg)

    ffprobe_bin = _require_binary("ffprobe")
    cmd = [
        ffprobe_bin,
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_name,sample_rate,channels,duration:format=duration,size",
        "-of",
        "json",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        msg = f"ffprobe failed on '{path}': {proc.stderr.strip()}"
        raise AudioValidationError(msg)

    payload = json.loads(proc.stdout)
    streams = payload.get("streams") or []
    if not streams:
        msg = f"No audio stream found in '{path}'."
        raise AudioValidationError(msg)

    stream = streams[0]
    fmt = payload.get("format") or {}
    duration_raw = stream.get("duration") or fmt.get("duration") or 0.0
    size_raw = fmt.get("size") or path.stat().st_size

    return AudioStats(
        path=path,
        sample_rate=int(stream.get("sample_rate", 0)),
        channels=int(stream.get("channels", 0)),
        codec_name=str(stream.get("codec_name", "unknown")),
        duration_seconds=float(duration_raw),
        size_bytes=int(size_raw),
    )


def normalise_audio(
    input_path: Path,
    output_path: Path,
    *,
    trim_start: float | None = None,
    trim_end: float | None = None,
) -> AudioStats:
    """Convert `input_path` to 24kHz mono 16-bit PCM WAV at `output_path` via `ffmpeg`."""
    if not input_path.exists():
        msg = f"Input audio file not found: {input_path}"
        raise FileNotFoundError(msg)

    if trim_start is not None and trim_start < 0:
        msg = f"trim_start must be >= 0 (got {trim_start})."
        raise AudioValidationError(msg)
    if trim_end is not None and trim_start is not None and trim_end <= trim_start:
        msg = f"trim_end ({trim_end}) must be greater than trim_start ({trim_start})."
        raise AudioValidationError(msg)

    ffmpeg_bin = _require_binary("ffmpeg")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd: list[str] = [ffmpeg_bin, "-y", "-hide_banner", "-loglevel", "error"]
    if trim_start is not None:
        cmd.extend(["-ss", f"{trim_start:.3f}"])
    if trim_end is not None:
        cmd.extend(["-to", f"{trim_end:.3f}"])

    cmd.extend(
        [
            "-i",
            str(input_path),
            "-vn",
            "-ac",
            str(RECOMMENDED_CHANNELS),
            "-ar",
            str(RECOMMENDED_SAMPLE_RATE_HZ),
            "-c:a",
            RECOMMENDED_CODEC,
            str(output_path),
        ]
    )

    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        msg = f"ffmpeg normalisation failed for '{input_path}': {proc.stderr.strip()}"
        raise AudioValidationError(msg)

    return inspect_audio(output_path)


def validate_reference_duration(stats: AudioStats) -> None:
    """Raise `AudioValidationError` if `stats` falls outside the 10.0-30.0s window."""
    if not stats.is_valid_reference_duration:
        msg = (
            f"Reference audio '{stats.path}' duration is {stats.duration_seconds:.2f}s; "
            f"Gemini Voice Replication requires between {MIN_REFERENCE_DURATION_SECONDS:.1f}s "
            f"and {MAX_REFERENCE_DURATION_SECONDS:.1f}s. "
            "Hint: pass '--trim-start' and '--trim-end' to 'voice-rep prep-audio'."
        )
        raise AudioValidationError(msg)


def export_mp3(
    wav_path: Path,
    mp3_path: Path,
    *,
    bitrate: str = "192k",
) -> Path:
    """Convert a WAV file to MP3 using `ffmpeg` and return `mp3_path`."""
    if not wav_path.exists():
        msg = f"WAV file not found: {wav_path}"
        raise FileNotFoundError(msg)

    ffmpeg_bin = _require_binary("ffmpeg")
    mp3_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        ffmpeg_bin,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(wav_path),
        "-codec:a",
        "libmp3lame",
        "-b:a",
        bitrate,
        str(mp3_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        msg = f"ffmpeg MP3 export failed for '{wav_path}': {proc.stderr.strip()}"
        raise AudioValidationError(msg)

    return mp3_path
