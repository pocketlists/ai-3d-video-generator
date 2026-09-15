# AI 3D Video Generator (v2.0)

A production-grade AI-powered automated 3D video generation system with Hermes Agent orchestration, real 3D asset API integration, Telegram failure escalation, and 20 parallel render workers.

## What's New in v2.0

- **Hermes Agent** — Central orchestration layer that coordinates all pipeline stages
- **Provider Abstraction** — Pluggable interfaces for LLM (Gemini/OpenAI), 3D Assets, TTS, Music, SFX, LipSync
- **3D Asset API** — Real 3D model generation/retrieval with caching (replaces primitive low-poly)
- **Telegram Escalation** — AI failures escalate to Telegram, wait for human/AI response, then resume
- **Google Free TTS** — Hindi, Hinglish, and English support via gTTS
- **20 Parallel Render Workers** — Dynamic frame partitioning across GitHub Actions matrix
- **CPU/RAM Monitoring** — Real metrics per render frame (not faked)
- **Asset Validation** — GLB/GLTF/FBX/OBJ validation before Blender assembly
- **Resumable State** — Pipeline can resume from last successful stage after failure

## Pipeline

```
Telegram → Hermes → AI Planning → Script → 3D Assets (cached)
  → Characters | Environments | Props | Voice | Music | SFX (parallel)
  → Animation → Camera → Lighting → Lip Sync → Blender → 20 Render Workers
  → Quality Check → FFmpeg → Telegram Delivery + Self-Optimize
```

## Quick Start

```bash
git clone https://github.com/pocketlists/ai-3d-video-generator.git
cd ai-3d-video-generator
pip install -r requirements.txt

# Set secrets
export TELEGRAM_BOT_TOKEN="your_token"
export TELEGRAM_CHANNEL_ID="your_channel"
export GEMINI_API_KEY="your_gemini_key"  # optional
export THREE_D_ASSET_API_KEY="your_key"  # optional
export THREE_D_ASSET_API_URL="your_url"  # optional

# Run smoke test
python scripts/smoke_test.py

# Run full pipeline
python -m controller.orchestrator --all

# Run specific stage
python -m controller.orchestrator --stage ai_planning
```

## GitHub Actions

1. Go to Actions tab → "01 - Receive Request" → Run workflow
2. Enter your video prompt
3. Pipeline chains through all 20 stages automatically

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Setup Guide](docs/SETUP.md)
- [Secrets](docs/SECRETS.md)
- [Pipeline](docs/PIPELINE.md)
- [File Manifest](FILE_MANIFEST.md)
- [Repository Audit](REPOSITORY_AUDIT.md)

## Testing

```bash
pytest tests/ -v
python scripts/smoke_test.py
```

## License

MIT
