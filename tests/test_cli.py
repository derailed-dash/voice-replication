"""Unit and integration tests for the agent-aware Typer CLI (`cli.py`)."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from voice_replication.cli import app
from voice_replication.config import Settings
from voice_replication.models import StorageMode, VoiceCatalogue, VoiceRecord, VoiceType
from voice_replication.storage import save_catalogue

runner = CliRunner()


class TestCliCommands:
    """Verify `--json` and `--dry-run` behaviour across CLI commands."""

    def test_prep_audio_normalises_and_outputs_json(
        self,
        tmp_path: Path,
        sample_reference_wav: Path,
        sample_consent_wav: Path,
        monkeypatch: object,
    ) -> None:
        settings = Settings(data_dir=tmp_path / "data", output_dir=tmp_path / "output")
        monkeypatch.setattr("voice_replication.cli._load_settings", lambda: settings)  # type: ignore[attr-defined]

        result = runner.invoke(
            app,
            [
                "prep-audio",
                str(sample_reference_wav),
                str(sample_consent_wav),
                "--alias",
                "dazbo",
                "--no-verify-consent",
                "--json",
            ],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert payload["alias"] == "dazbo"
        assert payload["source"]["sample_rate"] == 24000
        assert payload["source"]["channels"] == 1
        assert Path(payload["source"]["path"]).exists()
        assert Path(payload["consent"]["path"]).exists()

    def test_create_voice_dry_run_json(
        self,
        tmp_path: Path,
        sample_reference_wav: Path,
        sample_consent_wav: Path,
        monkeypatch: object,
    ) -> None:
        settings = Settings(data_dir=tmp_path / "data", output_dir=tmp_path / "output")
        monkeypatch.setattr("voice_replication.cli._load_settings", lambda: settings)  # type: ignore[attr-defined]

        result = runner.invoke(
            app,
            [
                "create",
                "--alias",
                "dazbo",
                "--display-name",
                "Dazbo Primary",
                "--source",
                str(sample_reference_wav),
                "--consent",
                str(sample_consent_wav),
                "--dry-run",
                "--json",
            ],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert payload["dry_run"] is True
        assert payload["alias"] == "dazbo"
        assert payload["storage_mode"] == "stateful"

    def test_list_inspect_refresh_and_delete_dry_run(
        self,
        tmp_path: Path,
        sample_reference_wav: Path,
        sample_consent_wav: Path,
        monkeypatch: object,
    ) -> None:
        settings = Settings(data_dir=tmp_path / "data", output_dir=tmp_path / "output")
        monkeypatch.setattr("voice_replication.cli._load_settings", lambda: settings)  # type: ignore[attr-defined]

        cat = VoiceCatalogue(project_id="test-gcp-project")
        cat.upsert(
            VoiceRecord(
                alias="dazbo",
                display_name="Dazbo Primary",
                voice_type=VoiceType.REPLICATED,
                storage_mode=StorageMode.STATEFUL,
                voice_id="voice_dazbo_001",
                source_audio_path=str(sample_reference_wav),
                consent_audio_path=str(sample_consent_wav),
            )
        )
        save_catalogue(cat, settings.catalogue_path)

        # 1. list (--json)
        list_res = runner.invoke(app, ["list", "--json"])
        assert list_res.exit_code == 0, list_res.output
        list_data = json.loads(list_res.stdout)
        assert len(list_data["voices"]) == 1
        assert list_data["voices"][0]["alias"] == "dazbo"

        # 2. list (Rich table human mode)
        list_human = runner.invoke(app, ["list"])
        assert list_human.exit_code == 0
        assert "dazbo" in list_human.stdout

        # 3. inspect (--json)
        insp_res = runner.invoke(app, ["inspect", "dazbo", "--json"])
        assert insp_res.exit_code == 0
        insp_data = json.loads(insp_res.stdout)
        assert insp_data["voice_id"] == "voice_dazbo_001"

        # 4. refresh (--dry-run --json)
        ref_res = runner.invoke(app, ["refresh", "dazbo", "--dry-run", "--json"])
        assert ref_res.exit_code == 0
        assert json.loads(ref_res.stdout)["dry_run"] is True

        # 5. delete (--dry-run --json)
        del_res = runner.invoke(app, ["delete", "dazbo", "--dry-run", "--json"])
        assert del_res.exit_code == 0
        assert json.loads(del_res.stdout)["dry_run"] is True

    def test_speak_and_dialogue_dry_run_json(
        self,
        tmp_path: Path,
        monkeypatch: object,
    ) -> None:
        settings = Settings(data_dir=tmp_path / "data", output_dir=tmp_path / "output")
        monkeypatch.setattr("voice_replication.cli._load_settings", lambda: settings)  # type: ignore[attr-defined]

        speak_res = runner.invoke(
            app,
            [
                "speak",
                "Hello Dazbo!",
                "--voice",
                "voice_abc123",
                "--style",
                "warm",
                "--output",
                str(tmp_path / "out.mp3"),
                "--dry-run",
                "--json",
            ],
        )
        assert speak_res.exit_code == 0, speak_res.output
        speak_data = json.loads(speak_res.stdout)
        assert speak_data["dry_run"] is True
        assert speak_data["output_format"] == "mp3"

        script_path = Path("examples/dialogue.yaml")
        diag_res = runner.invoke(
            app,
            [
                "dialogue",
                str(script_path),
                "--output",
                str(tmp_path / "dialogue.wav"),
                "--dry-run",
                "--json",
            ],
        )
        assert diag_res.exit_code == 0, diag_res.output
        diag_data = json.loads(diag_res.stdout)
        assert diag_data["dry_run"] is True
        assert len(diag_data["payload"]["input"][0]["content"]) == 3

    def test_gcs_preflight_and_init_dry_run(
        self,
        tmp_path: Path,
        monkeypatch: object,
    ) -> None:
        settings = Settings(
            gcs_bucket_name="test-voice-replication",
            data_dir=tmp_path / "data",
            output_dir=tmp_path / "output",
        )
        monkeypatch.setattr("voice_replication.cli._load_settings", lambda: settings)  # type: ignore[attr-defined]

        pre_res = runner.invoke(app, ["gcs-preflight", "--json"])
        assert pre_res.exit_code == 0
        pre_data = json.loads(pre_res.stdout)
        assert pre_data["bucket_name"] == "test-voice-replication"
        assert pre_data["default_storage_class"] == "COLDLINE"

        init_res = runner.invoke(app, ["gcs-init", "--dry-run", "--json"])
        assert init_res.exit_code == 0
        init_data = json.loads(init_res.stdout)
        assert init_data["dry_run"] is True

    def test_create_design_speak_dialogue_and_sync_full_paths(
        self,
        tmp_path: Path,
        sample_reference_wav: Path,
        sample_consent_wav: Path,
        monkeypatch: object,
    ) -> None:
        settings = Settings(data_dir=tmp_path / "data", output_dir=tmp_path / "output")
        monkeypatch.setattr("voice_replication.cli._load_settings", lambda: settings)  # type: ignore[attr-defined]

        class _StubVRClient:
            def __init__(self, **kwargs: object) -> None:
                self.client = object()

            def create_replicated_voice(self, **kwargs: object) -> VoiceRecord:
                return VoiceRecord(
                    alias=str(kwargs["alias"]),
                    display_name=str(kwargs["display_name"]),
                    voice_type=VoiceType.REPLICATED,
                    storage_mode=StorageMode.STATEFUL,
                    voice_id="voice_created_001",
                    source_audio_path=str(sample_reference_wav),
                    consent_audio_path=str(sample_consent_wav),
                )

            def create_designed_voice(self, **kwargs: object) -> VoiceRecord:
                return VoiceRecord(
                    alias=str(kwargs["alias"]),
                    display_name=str(kwargs["display_name"]),
                    voice_type=VoiceType.PROMPTED,
                    storage_mode=StorageMode.STATEFUL,
                    voice_id="voice_designed_002",
                    prompt=str(kwargs["prompt"]),
                )

            def list_remote_voices(self) -> list[dict[str, str]]:
                return [{"id": "voice_created_001", "display_name": "Dazbo", "type": "replicated"}]

            def delete_remote_voice(self, voice_id: str) -> None:
                pass

            def synthesise_single_speaker(self, **kwargs: object) -> Path:
                out = Path(str(kwargs["output_wav_path"]))
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(sample_consent_wav.read_bytes())
                return out

            def synthesise_dialogue(self, **kwargs: object) -> Path:
                out = Path(str(kwargs["output_wav_path"]))
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(sample_consent_wav.read_bytes())
                return out

        class _StubGCSManager:
            def __init__(self, **kwargs: object) -> None:
                pass

            def provision_bucket(self, *, dry_run: bool = False) -> dict[str, object]:
                return {"dry_run": dry_run, "created": True}

            def push(self, *, dry_run: bool = False) -> dict[str, object]:
                return {"direction": "push", "dry_run": dry_run, "uploaded": ["voices.json"]}

            def pull(self, *, dry_run: bool = False) -> dict[str, object]:
                return {"direction": "pull", "dry_run": dry_run, "downloaded": ["voices.json"]}

        monkeypatch.setattr("voice_replication.cli.VoiceReplicationClient", _StubVRClient)  # type: ignore[attr-defined]
        monkeypatch.setattr("voice_replication.cli.GCSBackupManager", _StubGCSManager)  # type: ignore[attr-defined]

        # 1. create (live stub, human mode)
        res_create = runner.invoke(
            app,
            [
                "create",
                "--alias",
                "dazbo",
                "--display-name",
                "Dazbo Primary",
                "--source",
                str(sample_reference_wav),
                "--consent",
                str(sample_consent_wav),
            ],
        )
        assert res_create.exit_code == 0, res_create.output

        # 2. design (dry-run + live stub)
        res_design_dry = runner.invoke(
            app,
            [
                "design",
                "--alias",
                "cohost",
                "--display-name",
                "CoHost",
                "--prompt",
                "Bright studio voice",
                "--dry-run",
            ],
        )
        assert res_design_dry.exit_code == 0
        res_design = runner.invoke(
            app,
            [
                "design",
                "--alias",
                "cohost",
                "--display-name",
                "CoHost",
                "--prompt",
                "Bright studio voice",
            ],
        )
        assert res_design.exit_code == 0

        # 3. list --remote --json & inspect human
        res_list = runner.invoke(app, ["list", "--remote", "--json"])
        assert res_list.exit_code == 0
        res_insp = runner.invoke(app, ["inspect", "dazbo"])
        assert res_insp.exit_code == 0

        # 4. refresh (live stub)
        res_ref = runner.invoke(app, ["refresh", "dazbo"])
        assert res_ref.exit_code == 0

        # 5. speak --file & dialogue (live stub)
        res_speak = runner.invoke(
            app,
            [
                "speak",
                "--file",
                "examples/monologue.md",
                "--voice",
                "dazbo",
                "--output",
                str(tmp_path / "monologue.wav"),
            ],
        )
        assert res_speak.exit_code == 0

        res_diag = runner.invoke(
            app,
            [
                "dialogue",
                "examples/dialogue.yaml",
                "--output",
                str(tmp_path / "diag.wav"),
            ],
        )
        assert res_diag.exit_code == 0

        # 6. gcs-preflight human, gcs-init, sync both
        assert runner.invoke(app, ["gcs-preflight"]).exit_code == 0
        assert runner.invoke(app, ["gcs-init"]).exit_code == 0
        assert runner.invoke(app, ["sync", "--direction", "both"]).exit_code == 0

        # 7. delete --remote
        assert runner.invoke(app, ["delete", "dazbo", "--remote"]).exit_code == 0

        # 8. Error hint paths
        err_missing = runner.invoke(app, ["inspect", "nonexistent", "--json"])
        assert err_missing.exit_code == 1
        assert "hint" in json.loads(err_missing.stdout)

        err_sync = runner.invoke(app, ["sync", "--direction", "invalid"])
        assert err_sync.exit_code == 1
