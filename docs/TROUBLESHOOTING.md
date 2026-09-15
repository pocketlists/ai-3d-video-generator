# Troubleshooting

## Common Issues

### 1. "PIPELINE_MODE=production" blocks template LLM fallback

**Cause**: The `PIPELINE_MODE` env var is set to `production` (or not set, which
defaults to production in some contexts).

**Fix**: For smoke tests and local dev, set `PIPELINE_MODE=test`:
```bash
export PIPELINE_MODE=test
```

For production: provide real `GEMINI_API_KEY` or `OPENAI_API_KEY`.

### 2. "Objaverse returned PROVIDER_UNAVAILABLE"

**Cause**: The `objaverse` Python package is not installed or network is unavailable.

**Fix**:
```bash
pip install objaverse
```

If the package is unavailable, the provider honestly reports
`PROVIDER_UNAVAILABLE` and the asset router tries the next provider.
It never returns an empty list as "success".

### 3. "Render worker: placeholder frames are NOT allowed in production"

**Cause**: `PIPELINE_MODE=production` + missing `.blend` file or Blender not installed.

**Fix**: Either install Blender (`sudo apt-get install -y blender`) or set
`PIPELINE_MODE=test` for smoke tests.

### 4. "TTS_PROVIDER=google_cloud: credentials not configured"

**Cause**: `GOOGLE_TTS_API_KEY` or `GOOGLE_APPLICATION_CREDENTIALS` not set.

**Fix**: Set credentials, or use `TTS_PROVIDER=gtts` for free TTS.
gTTS ≠ Google Cloud TTS — they are separate providers.

### 5. "Telegram escalation not sent"

**Cause**: `TELEGRAM_BOT_TOKEN` or `TELEGRAM_CHANNEL_ID` not configured.

**Fix**: Set both secrets. The resume token is still generated even if
delivery fails — it can be used with `resume.yml` manually.

### 6. "GitHub Actions: artifact not found"

**Cause**: A downstream job tries to download an artifact that wasn't uploaded.

**Fix**: Check that the upstream job succeeded and uploaded its artifact.
Use the artifact graph in `docs/ARTIFACT_GRAPH.md` to verify names match.

### 7. "Cross-run resume fails"

**Cause**: `STATE_BACKEND` is set to `local` (default for tests).

**Fix**: For production cross-run resume, set `STATE_BACKEND=contents` and
ensure `GITHUB_TOKEN` is available with `contents: write` permission.
The `pipeline-state` branch must exist.

### 8. "Dynamic render matrix generates wrong worker count"

**Cause**: `num_workers` input not set, or GitHub runner concurrency limits.

**Fix**: The `render_prepare` job computes `min(requested, 20)` and outputs
the matrix. Check the `render_prepare` job logs for `MATRIX_WORKERS=N`.
Actual concurrency depends on GitHub runner availability.

## Debug Mode

Set `PIPELINE_MODE=test` and `LOG_LEVEL=DEBUG` for verbose output:
```bash
export PIPELINE_MODE=test
export LOG_LEVEL=DEBUG
python -m controller.orchestrator --stage ai_planning
```

## Provider Status Check

```python
from providers.llm_provider import get_llm_provider
from providers.objaverse_provider import ObjaverseProvider
from providers.google_cloud_tts import GoogleCloudTTSProvider

# Check each provider's availability
print("LLM:", get_llm_provider({}).is_available())
print("Objaverse:", ObjaverseProvider({}).is_available())
print("Cloud TTS:", GoogleCloudTTSProvider({}).is_available())
```

## Known Limitations

- GitHub standard runners: CPU-only (no GPU) — Eevee on CPU is slow
- Objaverse: requires `pip install objaverse` + network
- Google Cloud TTS: requires paid credentials (gTTS is free but different)
- Blender full import: asset_importer's real import needs Blender runtime (bpy)
- Telegram: requires bot token + channel ID + allowed user IDs for security
