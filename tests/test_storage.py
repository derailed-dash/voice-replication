"""Unit tests for local catalogue persistence and GCS backup/sync (`storage.py`)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from voice_replication.config import Settings
from voice_replication.models import StorageMode, VoiceCatalogue, VoiceRecord, VoiceType
from voice_replication.storage import (
    GCSBackupManager,
    generate_bucket_architect_commands,
    load_catalogue,
    save_catalogue,
)


class _FakeBlob:
    def __init__(self, name: str) -> None:
        self.name = name
        self.storage_class: str | None = None
        self.content_bytes: bytes | None = None
        self.content_type: str | None = None

    def exists(self) -> bool:
        return self.content_bytes is not None

    def upload_from_string(self, data: str | bytes, content_type: str | None = None) -> None:
        self.content_bytes = data.encode("utf-8") if isinstance(data, str) else data
        self.content_type = content_type

    def upload_from_filename(self, filename: str) -> None:
        self.content_bytes = Path(filename).read_bytes()

    def download_as_text(self, encoding: str = "utf-8") -> str:
        assert self.content_bytes is not None
        return self.content_bytes.decode(encoding)

    def download_to_filename(self, filename: str) -> None:
        assert self.content_bytes is not None
        Path(filename).parent.mkdir(parents=True, exist_ok=True)
        Path(filename).write_bytes(self.content_bytes)


class _FakeBucket:
    def __init__(self, name: str) -> None:
        self.name = name
        self.storage_class = "STANDARD"
        self.blobs: dict[str, _FakeBlob] = {}

    def blob(self, blob_name: str) -> _FakeBlob:
        if blob_name not in self.blobs:
            self.blobs[blob_name] = _FakeBlob(blob_name)
        return self.blobs[blob_name]


class _FakeStorageClient:
    def __init__(self) -> None:
        self.buckets: dict[str, _FakeBucket] = {}

    def bucket(self, name: str) -> _FakeBucket:
        if name not in self.buckets:
            self.buckets[name] = _FakeBucket(name)
        return self.buckets[name]


class TestLocalCataloguePersistence:
    """Verify atomic load/save of `data/voices.json`."""

    def test_load_missing_catalogue_returns_empty_default(self, tmp_path: Path) -> None:
        cat_path = tmp_path / "data" / "voices.json"
        cat = load_catalogue(cat_path, project_id="test-gcp-project")
        assert cat.project_id == "test-gcp-project"
        assert cat.voices == {}

    def test_save_and_reload_catalogue_roundtrip(self, tmp_path: Path) -> None:
        cat_path = tmp_path / "data" / "voices.json"
        cat = VoiceCatalogue(project_id="test-gcp-project")
        cat.upsert(
            VoiceRecord(
                alias="dazbo",
                display_name="Dazbo Primary",
                voice_type=VoiceType.REPLICATED,
                storage_mode=StorageMode.STATEFUL,
                voice_id="voice_123",
            )
        )
        save_catalogue(cat, cat_path)
        assert cat_path.exists()

        reloaded = load_catalogue(cat_path)
        assert reloaded.get("dazbo") is not None
        assert reloaded.get("dazbo").voice_id == "voice_123"  # type: ignore[union-attr]


class TestGCSBackupManager:
    """Verify storage-class-aware GCS push/pull (`COLDLINE` WAVs + `STANDARD` `voices.json`)."""

    def test_push_sets_standard_on_catalogue_and_coldline_on_wavs(
        self,
        tmp_path: Path,
        sample_reference_wav: Path,
        sample_consent_wav: Path,
    ) -> None:
        settings = Settings(
            gcp_project_id="test-gcp-project",
            gcs_bucket_name="test-voice-replication",
            gcs_location="europe-west2",
            gcs_default_storage_class="COLDLINE",
            data_dir=tmp_path / "data",
        )
        cat = VoiceCatalogue(project_id=settings.gcp_project_id)
        cat.upsert(
            VoiceRecord(
                alias="dazbo",
                display_name="Dazbo Primary",
                voice_type=VoiceType.REPLICATED,
                storage_mode=StorageMode.STATEFUL,
                voice_id="voice_abc",
                source_audio_path=str(sample_reference_wav),
                consent_audio_path=str(sample_consent_wav),
            )
        )
        save_catalogue(cat, settings.catalogue_path)

        fake_gcs = _FakeStorageClient()
        manager = GCSBackupManager(settings=settings, storage_client=fake_gcs)
        report = manager.push(catalogue=cat)

        assert "voices.json" in report["uploaded"]
        assert "audio/dazbo/source.wav" in report["uploaded"]
        assert "audio/dazbo/consent.wav" in report["uploaded"]

        bucket = fake_gcs.bucket("test-voice-replication")
        assert bucket.blobs["voices.json"].storage_class == "STANDARD"
        assert bucket.blobs["audio/dazbo/source.wav"].storage_class == "COLDLINE"
        assert bucket.blobs["audio/dazbo/consent.wav"].storage_class == "COLDLINE"

    def test_pull_restores_catalogue_and_audio_files_to_new_workspace(
        self,
        tmp_path: Path,
        sample_reference_wav: Path,
        sample_consent_wav: Path,
    ) -> None:
        fake_gcs = _FakeStorageClient()
        settings_src = Settings(
            gcs_bucket_name="test-voice-replication",
            data_dir=tmp_path / "src_data",
        )
        cat = VoiceCatalogue(project_id="test-gcp-project")
        cat.upsert(
            VoiceRecord(
                alias="dazbo",
                display_name="Dazbo Primary",
                voice_type=VoiceType.REPLICATED,
                storage_mode=StorageMode.STATEFUL,
                voice_id="voice_abc",
                source_audio_path=str(sample_reference_wav),
                consent_audio_path=str(sample_consent_wav),
            )
        )
        manager_src = GCSBackupManager(settings=settings_src, storage_client=fake_gcs)
        manager_src.push(catalogue=cat)

        # Now pull into a clean destination data_dir
        settings_dst = Settings(
            gcs_bucket_name="test-voice-replication",
            data_dir=tmp_path / "dst_data",
        )
        manager_dst = GCSBackupManager(settings=settings_dst, storage_client=fake_gcs)
        pull_report = manager_dst.pull()

        assert "voices.json" in pull_report["downloaded"]
        assert (settings_dst.audio_dir_for_alias("dazbo") / "source.wav").exists()
        assert (settings_dst.audio_dir_for_alias("dazbo") / "consent.wav").exists()
        restored_cat = load_catalogue(settings_dst.catalogue_path)
        assert restored_cat.get("dazbo") is not None


class TestBucketArchitectCommands:
    """Verify attributed `gcloud` preflight and creation commands per GCS skill."""

    def test_generate_bucket_architect_commands_includes_attribution_and_flags(
        self, tmp_path: Path
    ) -> None:
        settings = Settings(
            gcp_project_id="test-gcp-project",
            gcs_bucket_name="test-voice-replication",
            gcs_location="europe-west2",
            gcs_default_storage_class="COLDLINE",
            data_dir=tmp_path / "data",
        )
        cmds: dict[str, Any] = generate_bucket_architect_commands(settings)
        assert "skill:google-cloud-storage-bucket-architect" in cmds["create_bucket_cmd"]
        assert "--location=europe-west2" in cmds["create_bucket_cmd"]
        assert "--default-storage-class=COLDLINE" in cmds["create_bucket_cmd"]
        assert "--uniform-bucket-level-access" in cmds["create_bucket_cmd"]
        assert "--public-access-prevention" in cmds["create_bucket_cmd"]
        assert "--soft-delete-duration=7d" in cmds["create_bucket_cmd"]
        assert len(cmds["preflight_cmds"]) >= 4
