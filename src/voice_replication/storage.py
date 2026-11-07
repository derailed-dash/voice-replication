"""Local `voices.json` catalogue persistence and Google Cloud Storage backup (`storage.py`).

Implements:
- Atomic read/write of `data/voices.json`.
- Storage-class-aware GCS synchronisation (`COLDLINE` default for rare-read
  master `.wav` files + `STANDARD` per-object override for `voices.json`).
- Attributed `gcloud` security preflight and bucket provisioning commands
  following the `google-cloud-storage-bucket-architect` and
  `google-cloud-storage-basics` skills.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from google.cloud import storage
from google.cloud.storage.bucket import EncryptionEnforcementConfig

from voice_replication.config import Settings
from voice_replication.models import VoiceCatalogue

GCS_ARCHITECT_ATTRIBUTION = (
    'CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+'
    "$CLOUDSDK_METRICS_ENVIRONMENT }gcs-skills gcs-skills/1.0 "
    '(skill:google-cloud-storage-bucket-architect)"'
)

CSEK_ENFORCEMENT_JSON = {
    "gmekEnforcement": {"restrictionMode": "NotRestricted"},
    "cmekEnforcement": {"restrictionMode": "NotRestricted"},
    "csekEnforcement": {"restrictionMode": "FullyRestricted"},
}


def load_catalogue(
    path: Path,
    *,
    project_id: str = "my-gcp-project",
) -> VoiceCatalogue:
    """Load `VoiceCatalogue` from `path`, or return a fresh empty catalogue if missing."""
    if not path.exists():
        return VoiceCatalogue(project_id=project_id)
    raw_json = path.read_text(encoding="utf-8")
    return VoiceCatalogue.model_validate_json(raw_json)


def save_catalogue(catalogue: VoiceCatalogue, path: Path) -> Path:
    """Atomically write `catalogue` to `path` as formatted JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(catalogue.model_dump_json(indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(path)
    return path


def generate_bucket_architect_commands(settings: Settings) -> dict[str, Any]:
    """Generate attributed `gcloud` preflight and creation commands for the GCS bucket."""
    project = settings.gcp_project_id
    bucket = settings.gcs_bucket_name
    location = settings.gcs_location
    storage_class = settings.gcs_default_storage_class

    preflight_cmds = [
        (
            f"{GCS_ARCHITECT_ATTRIBUTION} "
            f"gcloud org-policies describe constraints/gcp.restrictTLSVersion "
            f"--project={project} --effective --format=json"
        ),
        (
            f"{GCS_ARCHITECT_ATTRIBUTION} "
            f"gcloud org-policies describe constraints/storage.secureHttpTransport "
            f"--project={project} --effective --format=json"
        ),
        (
            f"{GCS_ARCHITECT_ATTRIBUTION} "
            f"gcloud org-policies describe constraints/storage.restrictAuthTypes "
            f"--project={project} --effective --format=json"
        ),
        (
            f"{GCS_ARCHITECT_ATTRIBUTION} "
            f"gcloud alpha resource-manager liens list --project={project} --format=json"
        ),
        (
            f"{GCS_ARCHITECT_ATTRIBUTION} "
            f"gcloud storage buckets describe gs://{bucket} --format=json"
        ),
    ]

    create_bucket_cmd = (
        f"{GCS_ARCHITECT_ATTRIBUTION} "
        f"gcloud storage buckets create gs://{bucket} "
        f"--project={project} "
        f"--location={location} "
        f"--default-storage-class={storage_class} "
        f"--uniform-bucket-level-access "
        f"--public-access-prevention "
        f"--soft-delete-duration=7d "
        f"--encryption-enforcement-file=encryption_enforcement.json"
    )

    update_labels_cmd = (
        f"{GCS_ARCHITECT_ATTRIBUTION} "
        f"gcloud storage buckets update gs://{bucket} "
        f"--project={project} "
        f"--update-labels=app=voice-replication,owner=dazbo"
    )

    return {
        "project_id": project,
        "bucket_name": bucket,
        "location": location,
        "default_storage_class": storage_class,
        "csek_enforcement_json": CSEK_ENFORCEMENT_JSON,
        "preflight_cmds": preflight_cmds,
        "create_bucket_cmd": create_bucket_cmd,
        "update_labels_cmd": update_labels_cmd,
    }


class GCSBackupManager:
    """Synchronises `voices.json` (`STANDARD`) and master WAVs (`COLDLINE`) with GCS."""

    def __init__(
        self,
        *,
        settings: Settings,
        storage_client: Any | None = None,
    ) -> None:
        self.settings = settings
        self.client: Any = (
            storage_client
            if storage_client is not None
            else storage.Client(project=settings.gcp_project_id)
        )

    def provision_bucket(self, *, dry_run: bool = False) -> dict[str, Any]:
        """Create the secure regional Coldline bucket in GCS via Python SDK."""
        plan = generate_bucket_architect_commands(self.settings)
        if dry_run:
            return {"dry_run": True, "created": False, "plan": plan}

        bucket = self.client.bucket(self.settings.gcs_bucket_name)
        bucket.storage_class = self.settings.gcs_default_storage_class
        bucket.iam_configuration.uniform_bucket_level_access_enabled = True
        bucket.iam_configuration.public_access_prevention = "enforced"
        bucket.soft_delete_policy.retention_duration_seconds = 604800  # 7 days
        bucket.encryption.customer_supplied_encryption_enforcement_config = (
            EncryptionEnforcementConfig(restriction_mode="FullyRestricted")
        )
        bucket.labels = {"app": "voice-replication", "owner": "dazbo"}

        self.client.create_bucket(bucket, location=self.settings.gcs_location)
        return {"dry_run": False, "created": True, "plan": plan}

    def push(
        self,
        *,
        catalogue: VoiceCatalogue | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Upload `voices.json` (`STANDARD`) and audio WAVs (`COLDLINE`) to GCS."""
        cat = catalogue or load_catalogue(
            self.settings.catalogue_path,
            project_id=self.settings.gcp_project_id,
        )
        bucket = self.client.bucket(self.settings.gcs_bucket_name)
        uploaded: list[str] = []
        skipped: list[str] = []

        # 1. Always store voices.json in STANDARD storage class to avoid early-deletion fees
        if not dry_run:
            cat_blob = bucket.blob("voices.json")
            cat_blob.storage_class = "STANDARD"
            cat_blob.upload_from_string(
                cat.model_dump_json(indent=2) + "\n",
                content_type="application/json",
            )
        uploaded.append("voices.json")

        # 2. Store rare-read master WAV files in COLDLINE (or configured default class)
        for record in cat.list_voices():
            for kind, local_str in (
                ("source.wav", record.source_audio_path),
                ("consent.wav", record.consent_audio_path),
            ):
                if not local_str:
                    continue
                local_path = Path(local_str)
                if not local_path.exists():
                    skipped.append(f"audio/{record.alias}/{kind} (missing locally)")
                    continue

                object_name = f"audio/{record.alias}/{kind}"
                if not dry_run:
                    wav_blob = bucket.blob(object_name)
                    wav_blob.storage_class = self.settings.gcs_default_storage_class
                    wav_blob.upload_from_filename(str(local_path))
                uploaded.append(object_name)

        return {
            "bucket": self.settings.gcs_bucket_name,
            "direction": "push",
            "dry_run": dry_run,
            "uploaded": uploaded,
            "skipped": skipped,
        }

    def pull(self, *, dry_run: bool = False) -> dict[str, Any]:
        """Download `voices.json` and any missing master WAV clips from GCS into local cache."""
        bucket = self.client.bucket(self.settings.gcs_bucket_name)
        downloaded: list[str] = []
        skipped: list[str] = []

        cat_blob = bucket.blob("voices.json")
        if not cat_blob.exists():
            return {
                "bucket": self.settings.gcs_bucket_name,
                "direction": "pull",
                "dry_run": dry_run,
                "downloaded": downloaded,
                "skipped": ["voices.json (not found in bucket)"],
            }

        remote_json = cat_blob.download_as_text(encoding="utf-8")
        remote_cat = VoiceCatalogue.model_validate_json(remote_json)
        downloaded.append("voices.json")

        for record in remote_cat.list_voices():
            alias_dir = self.settings.audio_dir_for_alias(record.alias)
            for kind, attr_name in (
                ("source.wav", "source_audio_path"),
                ("consent.wav", "consent_audio_path"),
            ):
                object_name = f"audio/{record.alias}/{kind}"
                wav_blob = bucket.blob(object_name)
                if not wav_blob.exists():
                    skipped.append(f"{object_name} (not in bucket)")
                    continue

                local_target = alias_dir / kind
                if not dry_run:
                    wav_blob.download_to_filename(str(local_target))
                setattr(record, attr_name, str(local_target))
                downloaded.append(object_name)

        if not dry_run:
            save_catalogue(remote_cat, self.settings.catalogue_path)

        return {
            "bucket": self.settings.gcs_bucket_name,
            "direction": "pull",
            "dry_run": dry_run,
            "downloaded": downloaded,
            "skipped": skipped,
        }
