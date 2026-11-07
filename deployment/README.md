# Deployment & Infrastructure Guide (`<your-project>`)

This guide covers configuring credentials, running the Google Cloud Storage security preflight checks, provisioning the Regional (`europe-west2`) Coldline backup bucket in `<your-project>`, and securing `.env` with `git-crypt`.

## Table of Contents

- [Prerequisites & Authentication](#prerequisites--authentication)
- [Environment Configuration (`.env` & `git-crypt`)](#environment-configuration-env--git-crypt)
- [GCS Security Preflight & Bucket Provisioning](#gcs-security-preflight--bucket-provisioning)
- [Backup & Restore Operations](#backup--restore-operations)

## Prerequisites & Authentication

1. **Google Cloud Project**: `<your-project>`
2. **Required APIs**:
   - Gemini Developer API (`generativelanguage.googleapis.com`)
   - Google Cloud Storage API (`storage.googleapis.com`)

```bash
# Authenticate gcloud and Application Default Credentials (ADC)
gcloud auth login
gcloud config set project <your-project>
gcloud auth application-default login

# Ensure Cloud Storage API is enabled
CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }gcs-skills gcs-skills/1.0 (skill:google-cloud-storage-basics)" \
gcloud services enable storage.googleapis.com --project=<your-project> --quiet
```

## Environment Configuration (`.env` & `git-crypt`)

Copy [.env.template](../.env.template) to `.env` and populate your `GEMINI_API_KEY` (created inside project `<your-project>` via [Google AI Studio](https://aistudio.google.com/apikey)):

```bash
cp .env.template .env
```

To maintain an encrypted copy (`.env.enc`) in Git using `git-crypt` (per [.gitattributes](../.gitattributes)):

```bash
# Unlock or initialise git-crypt in the repository
git-crypt init
git-crypt export-key ~/git-crypt-voice-replication.key

# Copy .env to .env.enc before committing so .env.enc is transparently encrypted by git-crypt
cp .env .env.enc
```

## GCS Security Preflight & Bucket Provisioning

Following the `google-cloud-storage-bucket-architect` workflow, inspect the project-level security posture and bucket creation plan using `voice-rep gcs-preflight`:

```bash
uv run voice-rep gcs-preflight
```

### 1. Project-Level Security Checks (`<your-project>`)

```bash
CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }gcs-skills gcs-skills/1.0 (skill:google-cloud-storage-bucket-architect)" \
gcloud org-policies describe constraints/gcp.restrictTLSVersion --project=<your-project> --effective --format=json

CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }gcs-skills gcs-skills/1.0 (skill:google-cloud-storage-bucket-architect)" \
gcloud org-policies describe constraints/storage.secureHttpTransport --project=<your-project> --effective --format=json

CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }gcs-skills gcs-skills/1.0 (skill:google-cloud-storage-bucket-architect)" \
gcloud org-policies describe constraints/storage.restrictAuthTypes --project=<your-project> --effective --format=json

CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }gcs-skills gcs-skills/1.0 (skill:google-cloud-storage-bucket-architect)" \
gcloud alpha resource-manager liens list --project=<your-project> --format=json
```

### 2. Provision the Regional Coldline Bucket (`europe-west2`)

You can provision the bucket either via the CLI SDK command:

```bash
# Preview first
uv run voice-rep gcs-init --dry-run

# Create gs://<voice-name>-voice-replication in europe-west2
uv run voice-rep gcs-init
```

Or directly via `gcloud storage`:

```bash
cat > encryption_enforcement.json << 'EOF'
{
  "gmekEnforcement": {"restrictionMode": "NotRestricted"},
  "cmekEnforcement": {"restrictionMode": "NotRestricted"},
  "csekEnforcement": {"restrictionMode": "FullyRestricted"}
}
EOF

CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }gcs-skills gcs-skills/1.0 (skill:google-cloud-storage-bucket-architect)" \
gcloud storage buckets create gs://<voice-name>-voice-replication \
    --project=<your-project> \
    --location=europe-west2 \
    --default-storage-class=COLDLINE \
    --uniform-bucket-level-access \
    --public-access-prevention \
    --soft-delete-duration=7d \
    --encryption-enforcement-file=encryption_enforcement.json

CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }gcs-skills gcs-skills/1.0 (skill:google-cloud-storage-bucket-architect)" \
gcloud storage buckets update gs://<voice-name>-voice-replication \
    --project=<your-project> \
    --update-labels=app=voice-replication,owner=dazbo

rm -f encryption_enforcement.json
```

## Backup & Restore Operations

```bash
# Push local voices.json (STANDARD class) and master WAVs (COLDLINE class) to GCS
uv run voice-rep sync --direction push

# Restore voices.json and master WAVs onto a new machine
uv run voice-rep sync --direction pull
```
