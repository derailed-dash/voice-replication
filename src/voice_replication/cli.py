"""Dual-mode Agent-Aware Rich/Typer CLI (`cli.py`).

Implements the `voice-rep` command-line interface following the `agent-aware-cli`
guidelines:
- **Human DX**: Tufte-style `rich` tables, semantic colour tokens, and clear step
  progress.
- **Agent AX**: Deterministic `--json` output on every command, `--dry-run`
  mutative safety on all state-changing operations, and copy-pasteable error
  hints written to `stderr`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from voice_replication.audio import (
    AudioValidationError,
    export_mp3,
    normalise_audio,
    validate_reference_duration,
)
from voice_replication.client import (
    VoiceReplicationClient,
    build_dialogue_payload,
    build_single_speaker_payload,
)
from voice_replication.config import Settings, get_settings
from voice_replication.consent import verify_consent_audio
from voice_replication.models import DialogueScript, VoiceType
from voice_replication.storage import (
    GCSBackupManager,
    generate_bucket_architect_commands,
    load_catalogue,
    save_catalogue,
)

app = typer.Typer(
    name="voice-rep",
    help=(
        "Personal Voice Replication & Expressive TTS Manager powered by "
        "Gemini 3.8 Flash TTS and Google Cloud Storage."
    ),
    no_args_is_help=True,
)


def _no_colour() -> bool:
    return bool(os.environ.get("NO_COLOR") or os.environ.get("VOICE_REP_NO_TUI"))


console = Console(no_color=_no_colour())
err_console = Console(stderr=True, no_color=_no_colour())


def _load_settings() -> Settings:
    """Return active `Settings` (isolated into a helper for clean test monkeypatching)."""
    return get_settings()


def _emit_json(payload: dict[str, Any]) -> None:
    """Print deterministic JSON to stdout."""
    typer.echo(json.dumps(payload, indent=2, default=str))


def _abort_with_hint(message: str, hint: str, *, as_json: bool = False) -> None:
    """Emit an actionable error message and hint, then exit with code 1."""
    if as_json:
        _emit_json({"error": message, "hint": hint})
    else:
        err_console.print(f"[bold red]Error:[/bold red] {message}")
        err_console.print(f"[yellow]Hint:[/yellow] {hint}")
    raise typer.Exit(code=1)


@app.command("prep-audio")
def prep_audio_cmd(
    raw_source: Annotated[
        Path,
        typer.Argument(help="Path to raw reference speaker recording (10-30s)."),
    ],
    raw_consent: Annotated[
        Path,
        typer.Argument(help="Path to raw mandatory consent statement recording."),
    ],
    alias: Annotated[
        str | None,
        typer.Option(
            "--alias",
            "-a",
            help="Voice alias under data/audio/<alias>/ (defaults to DEFAULT_VOICE_ALIAS).",
        ),
    ] = None,
    trim_start: Annotated[
        float | None,
        typer.Option("--trim-start", help="Optional start trim offset in seconds for source clip."),
    ] = None,
    trim_end: Annotated[
        float | None,
        typer.Option("--trim-end", help="Optional end trim offset in seconds for source clip."),
    ] = None,
    verify_consent: Annotated[
        bool,
        typer.Option(
            "--verify-consent/--no-verify-consent",
            help="Verify consent wording via gemini-3.5-transcribe.",
        ),
    ] = True,
    language_code: Annotated[
        str,
        typer.Option("--language", "-l", help="Consent statement language code."),
    ] = "en-GB",
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview target paths without running ffmpeg or STT."),
    ] = False,
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Emit deterministic JSON output."),
    ] = False,
) -> None:
    """Normalise reference and consent recordings to 24kHz mono 16-bit PCM WAV."""
    settings = _load_settings()
    resolved_alias = alias or settings.default_voice_alias
    target_dir = settings.audio_dir_for_alias(resolved_alias)
    out_source = target_dir / "source.wav"
    out_consent = target_dir / "consent.wav"

    if dry_run:
        result = {
            "dry_run": True,
            "alias": resolved_alias,
            "raw_source": str(raw_source),
            "raw_consent": str(raw_consent),
            "target_source": str(out_source),
            "target_consent": str(out_consent),
            "verify_consent": verify_consent,
        }
        if as_json:
            _emit_json(result)
        else:
            console.print(f"[cyan]Dry run:[/cyan] would normalise audio into {target_dir}")
        return

    try:
        src_stats = normalise_audio(
            raw_source,
            out_source,
            trim_start=trim_start,
            trim_end=trim_end,
        )
        validate_reference_duration(src_stats)
        consent_stats = normalise_audio(raw_consent, out_consent)
    except (FileNotFoundError, AudioValidationError, RuntimeError) as exc:
        _abort_with_hint(
            str(exc),
            (
                "Ensure input files exist and reference audio is 10-30s "
                "(or pass --trim-start/--trim-end)."
            ),
            as_json=as_json,
        )
        return

    consent_check_data: dict[str, Any] | None = None
    if verify_consent:
        vr_client = VoiceReplicationClient(api_key=settings.gemini_api_key or None)
        check = verify_consent_audio(
            out_consent,
            client=vr_client.client,
            language_code=language_code,
            model=settings.transcribe_model,
        )
        consent_check_data = check.model_dump(mode="json")
        if not check.passed:
            _abort_with_hint(
                f"Consent transcript similarity ({check.similarity:.2%}) below threshold. "
                f"Heard: '{check.transcript}'",
                f"Re-record reciting verbatim: '{check.expected_phrase}' "
                "or pass --no-verify-consent to bypass.",
                as_json=as_json,
            )

    payload: dict[str, Any] = {
        "alias": resolved_alias,
        "source": src_stats.model_dump(mode="json"),
        "consent": consent_stats.model_dump(mode="json"),
        "consent_verification": consent_check_data,
    }
    if as_json:
        _emit_json(payload)
    else:
        console.print(
            f"[green]Normalised 24kHz mono WAVs for '{resolved_alias}':[/green]\n"
            f"  Source:  {out_source} ({src_stats.duration_seconds:.1f}s)\n"
            f"  Consent: {out_consent} ({consent_stats.duration_seconds:.1f}s)"
        )


@app.command("create")
def create_cmd(
    alias: Annotated[
        str | None,
        typer.Option(
            "--alias",
            "-a",
            help="Local friendly alias (defaults to DEFAULT_VOICE_ALIAS from .env).",
        ),
    ] = None,
    display_name: Annotated[
        str | None,
        typer.Option(
            "--display-name",
            "-n",
            help="Display name stored in Gemini API (defaults to '<Alias> Primary').",
        ),
    ] = None,
    source: Annotated[
        Path | None,
        typer.Option(
            "--source",
            help="Path to 24kHz mono source.wav (defaults to data/audio/<alias>/source.wav).",
        ),
    ] = None,
    consent: Annotated[
        Path | None,
        typer.Option(
            "--consent",
            help="Path to 24kHz mono consent.wav (defaults to data/audio/<alias>/consent.wav).",
        ),
    ] = None,
    default_style: Annotated[
        str | None,
        typer.Option("--default-style", help="Default speech_metadata style prompt."),
    ] = "warm and conversational",
    model: Annotated[
        str | None,
        typer.Option("--model", "-m", help="Gemini TTS model (defaults to DEFAULT_TTS_MODEL)."),
    ] = None,
    language_code: Annotated[
        str,
        typer.Option("--language", "-l", help="BCP-47 language code."),
    ] = "en-GB",
    stateless: Annotated[
        bool,
        typer.Option(
            "--stateless",
            help="Use store=False to return a 7-day client-managed voicekey_... token.",
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Validate inputs without calling Gemini API."),
    ] = False,
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Emit deterministic JSON output."),
    ] = False,
) -> None:
    """Create a stateful (`store=True`) or stateless (`store=False`) replicated voice."""
    settings = _load_settings()
    resolved_alias = alias or settings.default_voice_alias
    resolved_display_name = display_name or f"{resolved_alias.capitalize()} Primary"
    resolved_model = model or settings.default_tts_model
    alias_dir = settings.audio_dir_for_alias(resolved_alias)
    src_path = source or (alias_dir / "source.wav")
    con_path = consent or (alias_dir / "consent.wav")

    if not src_path.exists() or not con_path.exists():
        _abort_with_hint(
            f"Missing audio files for alias '{resolved_alias}' ({src_path}, {con_path}).",
            f"Run: uv run voice-rep prep-audio <raw_ref> <raw_consent> --alias {resolved_alias}",
            as_json=as_json,
        )

    if dry_run:
        payload = {
            "dry_run": True,
            "alias": resolved_alias,
            "display_name": resolved_display_name,
            "model": resolved_model,
            "storage_mode": "stateless" if stateless else "stateful",
            "source_wav": str(src_path),
            "consent_wav": str(con_path),
        }
        if as_json:
            _emit_json(payload)
        else:
            console.print(
                f"[cyan]Dry run:[/cyan] would create voice '{resolved_alias}' "
                f"({resolved_display_name})."
            )
        return

    vr_client = VoiceReplicationClient(api_key=settings.gemini_api_key or None)
    record = vr_client.create_replicated_voice(
        alias=resolved_alias,
        display_name=resolved_display_name,
        source_wav_path=src_path,
        consent_wav_path=con_path,
        store=not stateless,
        model=resolved_model,
        default_style=default_style,
        language_code=language_code,
    )

    cat = load_catalogue(settings.catalogue_path, project_id=settings.gcp_project_id)
    cat.upsert(record)
    save_catalogue(cat, settings.catalogue_path)

    if as_json:
        _emit_json(record.model_dump(mode="json"))
    else:
        console.print(
            f"[green]Created voice '{record.alias}':[/green] {record.effective_token} "
            f"(expires {record.expires_at.date() if record.expires_at else 'N/A'})"
        )


@app.command("design")
def design_cmd(
    alias: Annotated[
        str,
        typer.Option("--alias", "-a", help="Local friendly alias for the designed voice."),
    ],
    display_name: Annotated[
        str,
        typer.Option("--display-name", "-n", help="Display name stored in Gemini API."),
    ],
    prompt: Annotated[
        str,
        typer.Option("--prompt", "-p", help="Natural-language vocal persona description."),
    ],
    gender: Annotated[
        str,
        typer.Option("--gender", help="Voice gender ('female', 'male', 'neutral')."),
    ] = "female",
    language_code: Annotated[
        str,
        typer.Option("--language", "-l", help="BCP-47 language code."),
    ] = "en-GB",
    default_style: Annotated[
        str | None,
        typer.Option("--default-style", help="Optional default style annotation."),
    ] = None,
    preview: Annotated[
        Path | None,
        typer.Option(
            "--preview", help="Optional path to save the returned sample_audio WAV preview."
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview request without calling Gemini API."),
    ] = False,
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Emit deterministic JSON output."),
    ] = False,
) -> None:
    """Create a persistent Voice Design (`type='prompted'`) co-host persona."""
    settings = _load_settings()
    if dry_run:
        payload = {
            "dry_run": True,
            "alias": alias,
            "display_name": display_name,
            "voice_type": "prompted",
            "prompt": prompt,
            "gender": gender,
            "language_code": language_code,
        }
        if as_json:
            _emit_json(payload)
        else:
            console.print(f"[cyan]Dry run:[/cyan] would design voice '{alias}'.")
        return

    vr_client = VoiceReplicationClient(api_key=settings.gemini_api_key or None)
    record = vr_client.create_designed_voice(
        alias=alias,
        display_name=display_name,
        prompt=prompt,
        gender=gender,
        language_code=language_code,
        default_style=default_style,
        preview_output_path=preview,
    )
    cat = load_catalogue(settings.catalogue_path, project_id=settings.gcp_project_id)
    cat.upsert(record)
    save_catalogue(cat, settings.catalogue_path)

    if as_json:
        _emit_json(record.model_dump(mode="json"))
    else:
        console.print(f"[green]Designed voice '{record.alias}':[/green] {record.effective_token}")


@app.command("list")
def list_cmd(
    remote: Annotated[
        bool,
        typer.Option("--remote", help="Also query live remote voices from Gemini API."),
    ] = False,
    voice_type: Annotated[
        VoiceType | None,
        typer.Option("--type", help="Filter by voice type (replicated or prompted)."),
    ] = None,
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Emit deterministic JSON output."),
    ] = False,
) -> None:
    """List voices registered in the local catalogue (and optionally remote Gemini API)."""
    settings = _load_settings()
    cat = load_catalogue(settings.catalogue_path, project_id=settings.gcp_project_id)
    records = cat.list_voices(voice_type=voice_type)

    remote_list: list[dict[str, Any]] | None = None
    if remote:
        vr_client = VoiceReplicationClient(api_key=settings.gemini_api_key or None)
        remote_list = vr_client.list_remote_voices()

    if as_json:
        _emit_json(
            {
                "project_id": cat.project_id,
                "voices": [r.model_dump(mode="json") for r in records],
                "remote_voices": remote_list,
            }
        )
        return

    table = Table(title=f"Voice Catalogue ({cat.project_id})")
    table.add_column("Alias", style="cyan", no_wrap=True)
    table.add_column("Display Name")
    table.add_column("Type", style="magenta")
    table.add_column("Mode")
    table.add_column("Identifier", style="green")
    table.add_column("TTL Days Left", justify="right")

    for rec in records:
        days_left = rec.days_until_expiry()
        ttl_str = f"{days_left}d" if days_left >= 0 else f"EXPIRED ({days_left}d)"
        table.add_row(
            rec.alias,
            rec.display_name,
            rec.voice_type.value,
            rec.storage_mode.value,
            rec.effective_token[:24],
            ttl_str,
        )
    console.print(table)


@app.command("inspect")
def inspect_cmd(
    alias: Annotated[str, typer.Argument(help="Local voice alias to inspect.")],
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Emit deterministic JSON output."),
    ] = False,
) -> None:
    """Inspect full metadata and TTL status for a single voice alias."""
    settings = _load_settings()
    cat = load_catalogue(settings.catalogue_path, project_id=settings.gcp_project_id)
    rec = cat.get(alias)
    if rec is None:
        _abort_with_hint(
            f"Voice alias '{alias}' not found in {settings.catalogue_path}.",
            "Run 'uv run voice-rep list' to see available voices.",
            as_json=as_json,
        )
        return

    data = rec.model_dump(mode="json")
    data["days_until_expiry"] = rec.days_until_expiry()
    data["is_expired"] = rec.is_expired()
    if as_json:
        _emit_json(data)
    else:
        for key, value in data.items():
            console.print(f"[cyan]{key}:[/cyan] {value}")


@app.command("refresh")
def refresh_cmd(
    alias: Annotated[str, typer.Argument(help="Voice alias to re-provision from master WAVs.")],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview refresh action without calling Gemini API."),
    ] = False,
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Emit deterministic JSON output."),
    ] = False,
) -> None:
    """Re-create a replicated voice from cached/GCS master WAVs to renew its 1-year TTL."""
    settings = _load_settings()
    cat = load_catalogue(settings.catalogue_path, project_id=settings.gcp_project_id)
    rec = cat.get(alias)
    if rec is None:
        _abort_with_hint(
            f"Voice alias '{alias}' not found in local catalogue.",
            "Run 'uv run voice-rep sync --direction pull' to restore from GCS first.",
            as_json=as_json,
        )
        return

    if dry_run:
        payload = {
            "dry_run": True,
            "action": "refresh",
            "alias": alias,
            "previous_voice_id": rec.voice_id,
            "source_audio_path": rec.source_audio_path,
            "consent_audio_path": rec.consent_audio_path,
        }
        if as_json:
            _emit_json(payload)
        else:
            console.print(f"[cyan]Dry run:[/cyan] would refresh voice '{alias}'.")
        return

    if not rec.source_audio_path or not rec.consent_audio_path:
        _abort_with_hint(
            f"Voice '{alias}' does not reference local source/consent WAV paths.",
            "Run 'uv run voice-rep sync --direction pull' to fetch master WAVs from GCS.",
            as_json=as_json,
        )
        return

    vr_client = VoiceReplicationClient(api_key=settings.gemini_api_key or None)
    refreshed = vr_client.create_replicated_voice(
        alias=rec.alias,
        display_name=rec.display_name,
        source_wav_path=Path(rec.source_audio_path),
        consent_wav_path=Path(rec.consent_audio_path),
        store=rec.storage_mode.value == "stateful",
        model=rec.model,
        default_style=rec.default_style,
        language_code=rec.language_code,
    )
    cat.upsert(refreshed)
    save_catalogue(cat, settings.catalogue_path)

    if as_json:
        _emit_json(refreshed.model_dump(mode="json"))
    else:
        console.print(
            f"[green]Refreshed voice '{alias}':[/green] new token {refreshed.effective_token}"
        )


@app.command("delete")
def delete_cmd(
    alias: Annotated[str, typer.Argument(help="Voice alias to delete.")],
    remote: Annotated[
        bool,
        typer.Option("--remote", help="Also delete the voice from the Gemini API project."),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview deletion without mutating state."),
    ] = False,
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Emit deterministic JSON output."),
    ] = False,
) -> None:
    """Remove a voice from the local catalogue (and optionally delete from Gemini API)."""
    settings = _load_settings()
    cat = load_catalogue(settings.catalogue_path, project_id=settings.gcp_project_id)
    rec = cat.get(alias)
    if rec is None:
        _abort_with_hint(
            f"Voice alias '{alias}' not found.",
            "Run 'uv run voice-rep list' to view registered aliases.",
            as_json=as_json,
        )
        return

    if dry_run:
        payload = {
            "dry_run": True,
            "action": "delete",
            "alias": alias,
            "remote": remote,
            "voice_id": rec.voice_id,
        }
        if as_json:
            _emit_json(payload)
        else:
            console.print(f"[cyan]Dry run:[/cyan] would delete voice '{alias}' (remote={remote}).")
        return

    if remote and rec.voice_id:
        vr_client = VoiceReplicationClient(api_key=settings.gemini_api_key or None)
        vr_client.delete_remote_voice(rec.voice_id)

    cat.remove(alias)
    save_catalogue(cat, settings.catalogue_path)

    if as_json:
        _emit_json({"deleted": alias, "remote_deleted": bool(remote and rec.voice_id)})
    else:
        console.print(f"[green]Deleted voice '{alias}'.[/green]")


@app.command("speak")
def speak_cmd(
    text: Annotated[
        str | None,
        typer.Argument(help="Inline text to synthesise (or omit when using --file)."),
    ] = None,
    file: Annotated[
        Path | None,
        typer.Option("--file", "-f", help="Path to a .txt or .md script file to synthesise."),
    ] = None,
    voice: Annotated[
        str | None,
        typer.Option(
            "--voice",
            "-v",
            help="Voice alias in catalogue or raw voice_... / Studio name (defaults to .env).",
        ),
    ] = None,
    style: Annotated[
        str | None,
        typer.Option("--style", "-s", help="Turn-level speech_metadata style instruction."),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option(
            "--model",
            "-m",
            help="Override TTS model (gemini-3.8-flash-tts or gemini-3.8-flash-lite-tts).",
        ),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output file path (.wav or .mp3)."),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run", help="Validate and preview Interactions API payload without calling API."
        ),
    ] = False,
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Emit deterministic JSON output."),
    ] = False,
) -> None:
    """Synthesise single-speaker speech using a replicated or prebuilt voice."""
    settings = _load_settings()
    resolved_voice_input = voice or settings.default_voice_alias
    resolved_output = output or (settings.output_dir / "speech.mp3")
    if file is not None:
        if not file.exists():
            _abort_with_hint(
                f"Script file not found: {file}",
                "Pass a valid .txt or .md file path to --file.",
                as_json=as_json,
            )
            return
        resolved_text = file.read_text(encoding="utf-8").strip()
    elif text is not None:
        resolved_text = text.strip()
    else:
        _abort_with_hint(
            "No text provided for speech synthesis.",
            "Pass inline text as an argument or specify '--file path/to/script.md'.",
            as_json=as_json,
        )
        return

    cat = load_catalogue(settings.catalogue_path, project_id=settings.gcp_project_id)
    rec = cat.get(resolved_voice_input)
    voice_token = rec.effective_token if rec is not None else resolved_voice_input
    effective_style = style or (rec.default_style if rec is not None else None)
    effective_model = model or (rec.model if rec is not None else settings.default_tts_model)
    out_fmt = "mp3" if resolved_output.suffix.lower() == ".mp3" else "wav"

    payload_preview = build_single_speaker_payload(
        text=resolved_text,
        voice_id_or_key=voice_token,
        model=effective_model,
        style=effective_style,
    )

    if dry_run:
        res = {
            "dry_run": True,
            "voice_input": resolved_voice_input,
            "resolved_voice": voice_token,
            "output_path": str(resolved_output),
            "output_format": out_fmt,
            "payload": payload_preview,
        }
        if as_json:
            _emit_json(res)
        else:
            console.print(
                f"[cyan]Dry run:[/cyan] would synthesise to {resolved_output} ({out_fmt})."
            )
        return

    vr_client = VoiceReplicationClient(api_key=settings.gemini_api_key or None)
    wav_target = resolved_output if out_fmt == "wav" else resolved_output.with_suffix(".wav")
    vr_client.synthesise_single_speaker(
        text=resolved_text,
        voice_id_or_key=voice_token,
        output_wav_path=wav_target,
        style=effective_style,
        model=effective_model,
    )
    if out_fmt == "mp3":
        final_path = export_mp3(wav_target, resolved_output)
        wav_target.unlink(missing_ok=True)
    else:
        final_path = wav_target

    if as_json:
        _emit_json({"output_path": str(final_path), "format": out_fmt, "voice": voice_token})
    else:
        console.print(f"[green]Synthesised audio saved to:[/green] {final_path}")


@app.command("dialogue")
def dialogue_cmd(
    script_path: Annotated[
        Path,
        typer.Argument(help="Path to multi-speaker YAML dialogue script."),
    ],
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output file path (.wav or .mp3)."),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run", help="Preview resolved multi-speaker payload without calling API."
        ),
    ] = False,
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Emit deterministic JSON output."),
    ] = False,
) -> None:
    """Synthesise a multi-speaker dialogue from a YAML script."""
    settings = _load_settings()
    resolved_output = output or (settings.output_dir / "dialogue.mp3")
    if not script_path.exists():
        _abort_with_hint(
            f"Dialogue YAML file not found: {script_path}",
            "Check 'examples/dialogue.yaml' for a sample script.",
            as_json=as_json,
        )
        return

    script = DialogueScript.from_yaml_file(script_path)
    cat = load_catalogue(settings.catalogue_path, project_id=settings.gcp_project_id)
    out_fmt = "mp3" if resolved_output.suffix.lower() == ".mp3" else "wav"
    payload_preview = build_dialogue_payload(script, catalogue=cat)

    if dry_run:
        res = {
            "dry_run": True,
            "script_path": str(script_path),
            "output_path": str(resolved_output),
            "output_format": out_fmt,
            "payload": payload_preview,
        }
        if as_json:
            _emit_json(res)
        else:
            console.print(f"[cyan]Dry run:[/cyan] would synthesise dialogue to {resolved_output}.")
        return

    vr_client = VoiceReplicationClient(api_key=settings.gemini_api_key or None)
    wav_target = resolved_output if out_fmt == "wav" else resolved_output.with_suffix(".wav")
    vr_client.synthesise_dialogue(script=script, output_wav_path=wav_target, catalogue=cat)
    if out_fmt == "mp3":
        final_path = export_mp3(wav_target, resolved_output)
        wav_target.unlink(missing_ok=True)
    else:
        final_path = wav_target

    if as_json:
        _emit_json({"output_path": str(final_path), "format": out_fmt})
    else:
        console.print(f"[green]Synthesised dialogue saved to:[/green] {final_path}")


@app.command("gcs-preflight")
def gcs_preflight_cmd(
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Emit deterministic JSON output."),
    ] = False,
) -> None:
    """Print attributed `gcloud` security preflight and Coldline bucket creation commands."""
    settings = _load_settings()
    plan = generate_bucket_architect_commands(settings)
    if as_json:
        _emit_json(plan)
        return

    console.print(
        "[bold cyan]GCS Bucket Architect Plan "
        f"({plan['project_id']} / {plan['location']}):[/bold cyan]"
    )
    console.print(f"  Bucket:        gs://{plan['bucket_name']}")
    console.print(
        f"  Default Class: {plan['default_storage_class']} (STANDARD override for voices.json)"
    )
    console.print("\n[bold]Preflight Commands:[/bold]")
    for cmd in plan["preflight_cmds"]:
        console.print(f"  {cmd}")
    console.print("\n[bold]Create Bucket Command:[/bold]")
    console.print(f"  {plan['create_bucket_cmd']}")


@app.command("gcs-init")
def gcs_init_cmd(
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview bucket provisioning plan without creating it."),
    ] = False,
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Emit deterministic JSON output."),
    ] = False,
) -> None:
    """Provision the regional Coldline GCS backup bucket configured in `.env`."""
    settings = _load_settings()
    if dry_run:
        plan = generate_bucket_architect_commands(settings)
        res = {"dry_run": True, "created": False, "plan": plan}
        if as_json:
            _emit_json(res)
        else:
            console.print(
                f"[cyan]Dry run:[/cyan] would create gs://{settings.gcs_bucket_name} "
                f"in {settings.gcs_location} ({settings.gcs_default_storage_class})."
            )
        return

    manager = GCSBackupManager(settings=settings)
    result = manager.provision_bucket(dry_run=False)
    if as_json:
        _emit_json(result)
    else:
        console.print(
            f"[green]Provisioned bucket gs://{settings.gcs_bucket_name} "
            f"in {settings.gcs_location}.[/green]"
        )


@app.command("sync")
def sync_cmd(
    direction: Annotated[
        str,
        typer.Option("--direction", "-d", help="Sync direction: 'push', 'pull', or 'both'."),
    ] = "push",
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run", help="Preview objects to upload/download without mutating state."
        ),
    ] = False,
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Emit deterministic JSON output."),
    ] = False,
) -> None:
    """Synchronise local `voices.json` (`STANDARD`) and master WAVs (`COLDLINE`) with GCS."""
    settings = _load_settings()
    if direction not in {"push", "pull", "both"}:
        _abort_with_hint(
            f"Invalid sync direction '{direction}'.",
            "Choose '--direction push', '--direction pull', or '--direction both'.",
            as_json=as_json,
        )
        return

    manager = GCSBackupManager(settings=settings)
    reports: list[dict[str, Any]] = []
    if direction in {"pull", "both"}:
        reports.append(manager.pull(dry_run=dry_run))
    if direction in {"push", "both"}:
        reports.append(manager.push(dry_run=dry_run))

    payload = {"direction": direction, "dry_run": dry_run, "reports": reports}
    if as_json:
        _emit_json(payload)
    else:
        for rep in reports:
            console.print(f"[green]GCS {rep['direction']}:[/green] {rep}")
