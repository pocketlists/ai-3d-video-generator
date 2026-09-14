# Setup Guide — AI 3D Video Generator

## Prerequisites

- Python 3.10+
- GitHub account with Actions enabled
- Telegram Bot Token and Channel ID
- (Optional) OpenAI API key for AI planning
- (Optional) ElevenLabs API key for high-quality TTS
- (Optional) Blender installed locally for testing

## Quick Start

### 1. Clone the Repository
```bash
git clone https://github.com/pocketlists/ai-3d-video-generator.git
cd ai-3d-video-generator
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Secrets

Copy the secrets template and add your values:
```bash
cp config/secrets_template.env .env
# Edit .env with your actual values
```

### 4. Set Environment Variables
```bash
export TELEGRAM_BOT_TOKEN="your_token"
export TELEGRAM_CHANNEL_ID="your_channel"
# Optional:
export OPENAI_API_KEY="your_key"
export ELEVENLABS_API_KEY="your_key"
```

### 5. Run Locally (Smoke Test)
```bash
python scripts/smoke_test.py
```

### 6. Run Full Pipeline Locally
```bash
python -m controller.orchestrator --all
```

### 7. Run a Specific Stage
```bash
python -m controller.orchestrator --stage ai_planning
```

## GitHub Actions Setup

### Required Secrets

Add these as repository secrets (Settings → Secrets and Variables → Actions):

| Secret | Required | Description |
|--------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | Telegram bot token |
| `TELEGRAM_CHANNEL_ID` | Yes | Telegram channel ID |
| `OPENAI_API_KEY` | No | For AI-powered planning |
| `ELEVENLABS_API_KEY` | No | For high-quality TTS |
| `HF_TOKEN` | No | HuggingFace token |
| `REPLICATE_API_TOKEN` | No | Replicate API token |

### Triggering the Pipeline

1. Go to the Actions tab in GitHub
2. Select "01 - Receive Request"
3. Click "Run workflow"
4. Enter your video prompt
5. The pipeline will chain through all 20 stages automatically

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=. --cov-report=html

# Run specific test
pytest tests/test_optimization.py -v
```

## Validation

```bash
# Validate all manifest files exist
python scripts/validate_repo.py
```
