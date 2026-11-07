.DEFAULT_GOAL := help
SHELL := /bin/bash

# Load configuration defaults from .env.template, then override with local .env if present
-include .env.template
-include .env

# Strip optional surrounding double/single quotes from .env values
unquote = $(patsubst "%",%,$(patsubst '%',%,$(1)))

GEMINI_API_KEY            := $(call unquote,$(GEMINI_API_KEY))
GCP_PROJECT_ID            := $(call unquote,$(GCP_PROJECT_ID))
GCS_BUCKET_NAME           := $(call unquote,$(GCS_BUCKET_NAME))
GCS_LOCATION              := $(call unquote,$(GCS_LOCATION))
GCS_DEFAULT_STORAGE_CLASS := $(call unquote,$(GCS_DEFAULT_STORAGE_CLASS))
DEFAULT_TTS_MODEL         := $(call unquote,$(DEFAULT_TTS_MODEL))
FAST_TTS_MODEL            := $(call unquote,$(FAST_TTS_MODEL))
TRANSCRIBE_MODEL          := $(call unquote,$(TRANSCRIBE_MODEL))
DEFAULT_VOICE_ALIAS       := $(call unquote,$(DEFAULT_VOICE_ALIAS))
DATA_DIR                  := $(call unquote,$(DATA_DIR))
OUTPUT_DIR                := $(call unquote,$(OUTPUT_DIR))

# Configurable CLI variables (defaulting to .env values; override on command line, e.g. `make speak ALIAS=custom`)
# Lowercase command-line overrides (e.g. `source=... consent=...`) are also accepted as fallbacks.
ALIAS        ?= $(or $(alias),$(DEFAULT_VOICE_ALIAS))
DISPLAY_NAME ?= $(display_name)
SOURCE       ?= $(source)
CONSENT      ?= $(consent)
LANGUAGE     ?= $(or $(language),en-GB)
STYLE        ?= $(or $(style),warm and conversational)
GENDER       ?= $(or $(gender),female)
TRIM_START   ?= $(trim_start)
TRIM_END     ?= $(trim_end)
FILE         ?= $(or $(file),examples/monologue.md)
TEXT         ?= $(text)
SCRIPT       ?= $(or $(script),examples/dialogue.yaml)
OUT          ?= $(or $(out),$(OUTPUT_DIR)/speech.mp3)
PREVIEW      ?= $(preview)
PROMPT       ?= $(or $(prompt),A warm, articulate British podcast co-host with a friendly conversational tone.)
MODEL        ?= $(or $(model),$(DEFAULT_TTS_MODEL))
FLAGS        ?= $(flags)

.PHONY: help install lint fix test test-live check clean \
        prep-audio create create-stateless design list list-remote inspect refresh delete delete-remote \
        speak dialogue gcs-preflight gcs-init sync-push sync-pull sync

help: ## Show this help message and active .env configuration
	@awk 'BEGIN {FS = ":.*##"; printf "\n\033[1mUsage:\033[0m\n  make \033[36m<target>\033[0m [VARIABLE=value ...]\n"} \
		/^[a-zA-Z0-9_-]+:.*?##/ { printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2 } \
		/^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)
	@printf "\n\033[1mActive .env Configuration:\033[0m\n"
	@printf "  GCP_PROJECT_ID=%s  GCS_BUCKET_NAME=gs://%s (%s, %s)\n" "$(GCP_PROJECT_ID)" "$(GCS_BUCKET_NAME)" "$(GCS_LOCATION)" "$(GCS_DEFAULT_STORAGE_CLASS)"
	@printf "  ALIAS=%s  MODEL=%s  DATA_DIR=%s  OUT=%s\n\n" "$(ALIAS)" "$(MODEL)" "$(DATA_DIR)" "$(OUT)"

##@ Development & Verification Gates

install: ## Create/sync virtual environment and install dependencies via uv
	uv sync --all-extras

lint: ## Run deterministic static checks (codespell, ruff check, pyright)
	uv run codespell -s
	uv run ruff check .
	uv run pyright

fix: ## Auto-fix formatting and lint issues via ruff and check spelling
	uv run ruff format .
	uv run ruff check --fix .
	uv run codespell -s

test: ## Run offline unit test suite with pytest and coverage
	uv run pytest -m "not live" --cov=voice_replication --cov-report=term-missing

test-live: ## Run live Gemini API / GCS integration tests (requires GEMINI_API_KEY in .env)
	uv run pytest -m "live" -v

check: ## Run full Tier 1 verification gate (codespell + ruff + pyright + pytest)
	uv run codespell -s
	uv run ruff check --fix .
	uv run pyright
	uv run pytest -m "not live" --cov=voice_replication --cov-report=term-missing

clean: ## Remove build, test, and ruff/pyright cache directories
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov dist build

##@ Audio Pre-Flight & Voice Lifecycle

prep-audio: ## Normalise reference & consent clips to 24kHz mono WAV and verify consent
	@if [ -z "$(SOURCE)" ] || [ -z "$(CONSENT)" ]; then \
		echo "Error: SOURCE and CONSENT paths are required. Example: make prep-audio SOURCE=raw/ref.m4a CONSENT=raw/consent.m4a ALIAS=$(ALIAS)" >&2; \
		exit 1; \
	fi
	uv run voice-rep prep-audio "$(SOURCE)" "$(CONSENT)" \
		--alias "$(ALIAS)" \
		--language "$(LANGUAGE)" \
		$(if $(TRIM_START),--trim-start $(TRIM_START),) \
		$(if $(TRIM_END),--trim-end $(TRIM_END),) \
		--verify-consent $(FLAGS)

create: ## Create a stateful replicated voice (store=True, 1-year TTL)
	uv run voice-rep create \
		--alias "$(ALIAS)" \
		$(if $(DISPLAY_NAME),--display-name "$(DISPLAY_NAME)",) \
		--language "$(LANGUAGE)" \
		--default-style "$(STYLE)" \
		$(if $(SOURCE),--source "$(SOURCE)",) \
		$(if $(CONSENT),--consent "$(CONSENT)",) \
		$(if $(MODEL),--model "$(MODEL)",) \
		$(FLAGS)

create-stateless: ## Create a stateless replicated voice_key (store=False, 7-day TTL)
	uv run voice-rep create \
		--alias "$(ALIAS)" \
		$(if $(DISPLAY_NAME),--display-name "$(DISPLAY_NAME)",) \
		--language "$(LANGUAGE)" \
		--default-style "$(STYLE)" \
		$(if $(SOURCE),--source "$(SOURCE)",) \
		$(if $(CONSENT),--consent "$(CONSENT)",) \
		$(if $(MODEL),--model "$(MODEL)",) \
		--stateless $(FLAGS)

design: ## Create a custom synthetic voice from a text prompt
	uv run voice-rep design \
		--alias "$(ALIAS)" \
		--display-name "$(or $(DISPLAY_NAME),$(ALIAS) Co-Host)" \
		--prompt "$(PROMPT)" \
		--gender "$(GENDER)" \
		--language "$(LANGUAGE)" \
		$(if $(STYLE),--default-style "$(STYLE)",) \
		$(if $(PREVIEW),--preview "$(PREVIEW)",) \
		$(FLAGS)

list: ## List all voices tracked in the local catalogue (data/voices.json)
	uv run voice-rep list $(FLAGS)

list-remote: ## List voices in both the local catalogue and live remote Gemini API
	uv run voice-rep list --remote $(FLAGS)

inspect: ## Inspect metadata, TTL countdown, and audio paths for ALIAS
	uv run voice-rep inspect "$(ALIAS)" $(FLAGS)

refresh: ## Renew a voice's 1-year TTL from master WAVs
	uv run voice-rep refresh "$(ALIAS)" $(FLAGS)

delete: ## Delete a voice from the local catalogue
	uv run voice-rep delete "$(ALIAS)" $(FLAGS)

delete-remote: ## Delete a voice from both remote Gemini API and local catalogue
	uv run voice-rep delete "$(ALIAS)" --remote $(FLAGS)

##@ Speech & Dialogue Synthesis

speak: ## Synthesise single-speaker audio (FILE=examples/monologue.md or TEXT="...")
	@mkdir -p "$$(dirname "$(OUT)")"
	uv run voice-rep speak \
		$(if $(TEXT),"$(TEXT)",--file "$(FILE)") \
		--voice "$(ALIAS)" \
		$(if $(STYLE),--style "$(STYLE)",) \
		$(if $(MODEL),--model "$(MODEL)",) \
		--output "$(OUT)" $(FLAGS)

dialogue: ## Synthesise multi-speaker dialogue from YAML (SCRIPT=examples/dialogue.yaml)
	@mkdir -p "$$(dirname "$(OUT)")"
	uv run voice-rep dialogue "$(SCRIPT)" \
		--output "$(OUT)" $(FLAGS)

##@ Google Cloud Storage (GCS) Backup & Recovery

gcs-preflight: ## Display read-only gcloud pre-flight verification commands
	uv run voice-rep gcs-preflight $(FLAGS)

gcs-init: ## Provision regional GCS backup bucket
	uv run voice-rep gcs-init $(FLAGS)

sync-push: ## Push local voices.json and audio WAVs to GCS
	uv run voice-rep sync --direction push $(FLAGS)

sync-pull: ## Pull voices.json and missing audio WAVs from GCS
	uv run voice-rep sync --direction pull $(FLAGS)

sync: ## Bi-directionally synchronise local catalogue and audio WAVs with GCS
	uv run voice-rep sync --direction both $(FLAGS)
