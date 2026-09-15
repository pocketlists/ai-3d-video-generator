# AI 3D Video Generator (v4.0)

Production-hardened AI-powered 3D video generation pipeline with Hermes Agent
orchestration, persistent state, Telegram escalation with resume tokens, and
deterministic parallel rendering.

## What's New in v4.0

- **blender/asset_importer.py** — GLB/GLTF/OBJ/FBX import with validation
  (inside Blender: real import + normalization; outside: honest file-level checks)
- **providers/google_cloud_tts.py** — real Google Cloud TTS provider,
  clearly separated from free gTTS (no silent substitution)
- **PIPELINE_MODE guard everywhere** — production can never produce
  placeholder frames, template LLM plans, or procedural cubes silently
- **Dynamic render matrix** — pipeline.yml generates the worker matrix from
  the actual worker count (render_prepare job + fromJSON); matrix always
  matches frame partitions
- **Honest Objaverse** — returns PROVIDER_UNAVAILABLE (not silent empty
  lists) when the retrieval library is missing
- **Real cross-run persistence** — GitHubContentsStateStore commits state
  via gh api (not just local files labeled "GitHub")
- **render_manifest.json checksums** — per-frame sha256 for corruption
  detection and hash-based reuse
- **18 broken legacy workflows deleted** — the master pipeline.yml is the
  ONE canonical pipeline (legacy `gh workflow run` chains could not share
  artifacts across runs)
- 26 new regression tests (200 total) covering partition/matrix match,
  state persistence across runners, Telegram resume flow, production
  guards, asset importer, checksums, TTS separation

## Honest Status (v3.0)

### FULLY IMPLEMENTED (locally verified)
- Master pipeline workflow (`pipeline.yml`) — single run, job-level `needs:`, artifacts passed between jobs
- Resume workflow (`resume.yml`) — external-response resume with job_id + resume_token validation
- Persistent state storage (`core/storage.py`) — local / artifact / repository backends
- Atomic checkpoint system (`controller/checkpoint.py`)
- State machine with valid transitions (`controller/state_manager.py`)
- Error classification with retry policy (`utils/error_classifier.py`)
- LLM provider abstraction — Gemini/OpenAI/Template, **no silent fallback**
- Style-aware planning (anime, cinematic, realistic, fantasy, low-poly, ...)
- Telegram escalation with RESUME_TOKEN, **no 5-minute timeout**, runner exits cleanly
- Telegram reply parsing (message, channel post, reply, edited) with user authorization
- Render partitioning — dynamic, deterministic, no overlap/missing frames
- Render collector — preserves worker identity, detects duplicates/missing, render_manifest.json
- FFmpeg pipeline — no silent audio fallback, single final encode, structured FFmpegError
- CPU/RAM monitoring with real measurements (psutil)
- Mock providers for testing (`tests/mocks.py`) — tests run without paid APIs
- 35+ new regression tests (state machine, checkpoint, partitioning, collector, escalation, classifier)
- Smoke test (10 end-to-end checks)
- Deep repo validator (syntax, YAML, secrets scan, TODO scan, imports)

### PROVIDER_DEPENDENT (requires credentials — interface implemented, not testable here)
- **Gemini planning** — requires `GEMINI_API_KEY` (structured JSON, validated)
- **Objaverse asset retrieval** — requires network + annotations access; search/rank/download implemented, dataset indexing is documented limitation
- **External 3D Asset API** — requires `THREE_D_ASSET_API_KEY`/`URL`; capability detection implemented
- **Google Cloud TTS** — separate from gTTS; requires Google credentials
- **Telegram delivery** — requires `TELEGRAM_BOT_TOKEN`/`CHANNEL_ID`

### OPTIONAL / FALLBACK ONLY
- TemplateProvider planning — only when `LLM_PROVIDER=template` or `ALLOW_TEMPLATE_FALLBACK=true`
- Procedural low-poly assets — smoke tests and explicit fallback ONLY, never silent production substitute

### KNOWN LIMITATIONS (honestly stated)
- GitHub standard runners: CPU-only, no GPU; Eevee renders are slow for 1440 frames
- Actual parallel workers depend on GitHub runner concurrency (requested ≠ actual)
- Objaverse-XL annotations are very large; production search needs pre-indexed subset or the objaverse library
- gTTS is free-tier Google Translate TTS — NOT Google Cloud Text-to-Speech, has rate limits
- Telegram bot API file upload limit: 50MB
- Blender 4.2+ uses EEVEE_NEXT (version-aware engine selection implemented)

## Architecture

```
Telegram / Workflow Dispatch
        ↓
   Hermes Agent (decisions: provider, retry, escalate, resume)
        ↓
   Controller (state machine + checkpoints)
        ↓
   Workers (20 stages)
        ↓
   Providers (LLM / Asset / TTS / Music / SFX / LipSync) + Blender + FFmpeg
        ↓
   Results → Hermes → Telegram delivery
```

On critical failure: retry (classified) → checkpoint → Telegram escalation
(with JOB_ID, STAGE, ERROR, PROVIDER, RESUME_TOKEN) → state =
WAITING_FOR_EXTERNAL_RESPONSE → **runner exits** (no waiting) → future reply
triggers `resume.yml` → validates token → resumes exact failed stage.

## Quick Start

```bash
git clone https://github.com/pocketlists/ai-3d-video-generator.git
cd ai-3d-video-generator
pip install -r requirements.txt

# No credentials needed for tests (mocks):
pytest tests/ -v
python scripts/smoke_test.py
python scripts/validate_repo.py
```

## Production Setup (GitHub Secrets)

| Secret | Required | Purpose |
|--------|----------|---------|
| `TELEGRAM_BOT_TOKEN` | For delivery | Bot token |
| `TELEGRAM_CHANNEL_ID` | For delivery | Target channel |
| `TELEGRAM_ALLOWED_USER_IDS` | Recommended | Authorized resume users |
| `GEMINI_API_KEY` | For AI planning | Gemini API |
| `THREE_D_ASSET_API_KEY`/`URL` | For real 3D assets | External provider |
| `HF_TOKEN` | For Objaverse | HuggingFace access |

## Trigger

Actions → "AI Video Pipeline (Master)" → Run workflow → prompt + style +
workers + quality profile.

## Documentation

- [Initial Audit (v2 bugs found)](docs/INITIAL_AUDIT.md)
- [Failure Matrix](docs/FAILURE_MATRIX.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Setup](docs/SETUP.md)
- [Secrets](docs/SECRETS.md)
- [Pipeline](docs/PIPELINE.md)
- [File Manifest](FILE_MANIFEST.md)
- [Repository Audit](REPOSITORY_AUDIT.md)

## License

MIT
