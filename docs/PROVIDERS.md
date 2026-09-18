# Provider Architecture

## Interface Contract (PHASE 57)

Every provider exposes:

- `is_available()` — credentials/network present
- `capabilities()` — feature support dict (never faked)
- `health_check()` — live check

Structured errors with classification (utils/error_classifier.py):
TRANSIENT, RATE_LIMIT, AUTH, PERMISSION, INVALID_INPUT,
PROVIDER_UNAVAILABLE, TIMEOUT, OUT_OF_MEMORY, BLENDER_ERROR,
FFMPEG_ERROR, QUALITY_FAILURE, HUMAN_INTERVENTION, INTERNAL_ERROR.

## Providers

| Provider | File | Status |
|----------|------|--------|
| LLMProvider (Gemini/OpenAI/Template) | providers/llm_provider.py | Gemini/OpenAI PROVIDER_DEPENDENT |
| AssetProvider (external 3D API) | providers/asset_provider.py | PROVIDER_DEPENDENT |
| ObjaverseProvider | providers/objaverse_provider.py | PROVIDER_DEPENDENT (needs objaverse package) |
| AssetRouter | providers/asset_router.py | IMPLEMENTED |
| TTSProvider (gTTS/Espeak) | providers/tts_provider.py | gTTS free-tier |
| GoogleCloudTTSProvider | providers/google_cloud_tts.py | PROVIDER_DEPENDENT (needs credentials) |
| MusicProvider / SFXProvider | providers/audio_provider.py | IMPLEMENTED (procedural) |
| LipSyncProvider | providers/lip_sync_provider.py | IMPLEMENTED (simple viseme — NOT claimed advanced) |
| StorageProvider | core/storage.py | IMPLEMENTED (4 backends) |

## No Silent Fallback Rules

- `LLM_PROVIDER=gemini` + failure → retry → escalate → WAITING. Template
  ONLY if `LLM_PROVIDER=template` OR (`ALLOW_TEMPLATE_FALLBACK=true` AND
  `PIPELINE_MODE=test`).
- `TTS_PROVIDER=google_cloud` without credentials → clear error. NO silent
  gTTS substitution (gTTS ≠ Google Cloud TTS).
- Objaverse unavailable → PROVIDER_UNAVAILABLE status, router tries next
  configured provider. Never a silent empty success.

## Mocks (tests/mocks.py) — TEST ONLY

MockGeminiProvider, MockFailingGeminiProvider, MockObjaverseProvider,
MockTTSProvider, MockTelegramProvider. Mocks are never selected in
production — they live only under tests/ and are used explicitly.


## TTS Providers (voice)

| Provider | Config value | Credentials | Notes |
|----------|--------------|-------------|-------|
| Gemini TTS | `TTS_PROVIDER=gemini_tts` | `GEMINI_API_KEY` (same as planning) | Models: `gemini-2.5-flash-preview-tts`, `gemini-2.5-pro-preview-tts`, `gemini-3.1-flash-tts-preview`. 30 prebuilt voices (`GEMINI_TTS_VOICE`, default `Kore`). Hindi/Hinglish follows input text. Recommended default. |
| Google Cloud TTS | `TTS_PROVIDER=google_cloud` | `GOOGLE_TTS_API_KEY` | Separate product from gTTS. |
| gTTS | `TTS_PROVIDER=gtts` | none (free) | Google Translate TTS — NOT Google Cloud TTS. |
| ElevenLabs | `TTS_PROVIDER=elevenlabs` | `ELEVENLABS_API_KEY` | Premium voices. |

No silent fallback between providers — an explicitly requested provider that is
unavailable raises a clear error.
