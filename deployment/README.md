# Deployment & Infrastructure Guide (`<your-project>`)

This guide covers creating and configuring a Google Cloud project (`<your-project>`), enabling all required APIs, provisioning a Gemini API key, sharing replicated voices with collaborators in Google AI Studio, running the Google Cloud Storage security pre-flight checks, provisioning the Regional (`europe-west2`) Coldline backup bucket, and securing `.env` with `git-crypt`.

## Table of Contents

- [Prerequisites & API Enablement](#prerequisites--api-enablement)
- [Creating a Gemini API Key](#creating-a-gemini-api-key)
- [Environment Configuration (`.env` & `git-crypt`)](#environment-configuration-env--git-crypt)
- [Sharing the Project & Voices with a Collaborator / Co-Host in Google AI Studio](#sharing-the-project--voices-with-a-collaborator--co-host-in-google-ai-studio)
- [GCS Security Pre-Flight & Bucket Provisioning](#gcs-security-pre-flight--bucket-provisioning)
- [Backup & Restore Operations](#backup--restore-operations)

## Prerequisites & API Enablement

Stateful replicated voices (`store=True`) and Voice Design personas (`type="prompted"`) are scoped to the Google Cloud project associated with your `GEMINI_API_KEY`. A new project requires three Google Cloud APIs enabled:

| API Service Name | Purpose |
| :--- | :--- |
| `generativelanguage.googleapis.com` | **Gemini Developer API** — Required for Voice Replication (`POST /v1beta/voices`), Voice Design, TTS speech synthesis (`gemini-3.8-flash-tts`), and consent verification (`gemini-3.5-transcribe`). |
| `storage.googleapis.com` | **Google Cloud Storage API** — Required for the Regional (`europe-west2`) backup bucket (`COLDLINE` master `.wav` recordings and `STANDARD` `voices.json` catalogue). |
| `apikeys.googleapis.com` | **API Keys API** — Required when creating, listing, or restricting API keys programmatically via `gcloud services api-keys`. |

### 1. Create the GCP Project & Link Billing (Mandatory for Paid Quota Tier 1 & GCS)

> **Important**: Linking an active Cloud Billing account is **mandatory** for both:
> 1. **Gemini Voice Replication (`gemini-3.8-flash-tts`)**, which requires **Paid Quota Tier 1 or higher** (calling `voices.create` on an unbilled Free Quota Tier project fails with `403 PERMISSION_DENIED: Voice replication on model models/gemini-3.8-flash-tts requires Paid Quota Tier 1 or higher`).
> 2. **Google Cloud Storage bucket creation (`make gcs-init`)**.

```bash
# Authenticate gcloud and Application Default Credentials (ADC)
gcloud auth login
gcloud auth application-default login

# Create a new Google Cloud project (skip if <your-project> already exists)
gcloud projects create <your-project> --name="Voice Replication"
gcloud config set project <your-project>

# List your available billing accounts and link one (MANDATORY for Paid Tier 1 + GCS)
gcloud billing accounts list
gcloud billing projects link <your-project> --billing-account=<your-billing-account-id>
```

### 2. Enable Required APIs

```bash
# Enable Gemini Developer API, Cloud Storage API, and API Keys API
CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }gcs-skills gcs-skills/1.0 (skill:google-cloud-storage-basics)" \
gcloud services enable \
    generativelanguage.googleapis.com \
    storage.googleapis.com \
    apikeys.googleapis.com \
    --project=<your-project> \
    --quiet
```

## Creating a Gemini API Key

You can create a `GEMINI_API_KEY` bound to `<your-project>` either in the Google AI Studio browser UI or directly via `gcloud`:

### Option A: Via Google AI Studio (Recommended)

1. Open [Google AI Studio — API Keys](https://aistudio.google.com/apikey).
2. Click **Create API key**, select your Google Cloud project (`<your-project>`), and copy the generated key into `.env`.

### Option B: Via `gcloud services api-keys`

When creating an API key on a brand-new project before updating your default `gcloud` quota project, pass `--billing-project=<your-project>` alongside `--project=<your-project>`:

```bash
gcloud services api-keys create \
    --project=<your-project> \
    --billing-project=<your-project> \
    --display-name="voice-replication-cli" \
    --api-target=service=generativelanguage.googleapis.com
```

## Environment Configuration (`.env` & `git-crypt`)

Copy [.env.template](../.env.template) to `.env` and populate your `GEMINI_API_KEY`, `GCP_PROJECT_ID`, and `GCS_BUCKET_NAME`:

```bash
cp .env.template .env
```

### Encrypting `.env` -> `.env.enc` with Shared `git-crypt` Key

This repository uses [.gitattributes](../.gitattributes) (`*.enc filter=git-crypt diff=git-crypt`) alongside a single shared symmetric key at `~/localdev/git-crypt-key` across repositories. **Never** run `git-crypt init` to mint a new per-repository key when `~/localdev/git-crypt-key` already exists.

```bash
# 1. Unlock the repository using the shared symmetric key (on a clean working tree)
git-crypt unlock ~/localdev/git-crypt-key

# 2. Synchronise plaintext .env to encrypted .env.enc before committing
~/.gemini/config/skills/secrets-with-git-crypt/scripts/git-crypt-helper.sh sync-to-enc .env
# Or directly:
cp .env .env.enc

# 3. Verify encryption status on staged/tracked files
git-crypt status -e
```

## Sharing the Project & Voices with a Collaborator / Co-Host in Google AI Studio

When you create a replicated voice with `store=True` (via `make create`), the resulting `voice_...` resource is stored at the **Google Cloud project level** inside `<your-project>` (up to 200 custom voices per project, with a 1-year TTL).

To allow a co-host or collaborator (for example, Kate) to access and use all stored voices in the [Google AI Studio Speech Playground](https://aistudio.google.com/generate-speech) from their own Google account:

### 1. Grant Least-Privilege Project IAM Roles (No New API Key Needed)

The collaborator does **not** need to create their own API key. By granting read/viewer access to the project and existing API key (`roles/viewer`, `roles/serviceusage.apiKeysViewer`, and `roles/serviceusage.serviceUsageConsumer`), they can select the existing project key in Google AI Studio (inheriting any spend cap or API restrictions configured on that key) without being able to mint new keys or modify infrastructure:

```bash
# 1. Allow the collaborator to view the project in Google AI Studio
gcloud projects add-iam-policy-binding <your-project> \
    --member="user:collaborator@example.com" \
    --role="roles/viewer"

# 2. Allow the collaborator to select the existing project API key in AI Studio
gcloud projects add-iam-policy-binding <your-project> \
    --member="user:collaborator@example.com" \
    --role="roles/serviceusage.apiKeysViewer"

# 3. Allow the collaborator to consume enabled project services
gcloud projects add-iam-policy-binding <your-project> \
    --member="user:collaborator@example.com" \
    --role="roles/serviceusage.serviceUsageConsumer"
```

*(Alternatively, if the collaborator also needs to create new API keys or manage project resources, grant `roles/editor` instead.)*

If the collaborator also needs to pull/push the master `.wav` backups and `voices.json` catalogue from the GCS bucket via `make sync`:

```bash
gcloud storage buckets add-iam-policy-binding gs://<voice-name>-voice-replication \
    --member="user:collaborator@example.com" \
    --role="roles/storage.objectAdmin"
```

### 2. Accessing the Shared Voices in Google AI Studio

1. The collaborator opens [https://aistudio.google.com/generate-speech](https://aistudio.google.com/generate-speech) signed in with their Google account.
2. They click the **API key / project** selector at the top of the Playground and choose the existing API key inside **`<your-project>`** (no new API key creation required).
3. They click **`+ Create new dialog`** -> **`Open voice settings`**, and every stateful voice registered in `<your-project>` (e.g. **Dazbo Primary** and **Kate Primary**) automatically appears at the very top of the **Available voices** list for both single-speaker and multi-speaker dialogues.

## GCS Security Pre-Flight & Bucket Provisioning

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
make sync-push

# Restore voices.json and master WAVs onto a new machine
make sync-pull

# Bi-directionally synchronise local cache and GCS (pull missing, then push local)
make sync
```
