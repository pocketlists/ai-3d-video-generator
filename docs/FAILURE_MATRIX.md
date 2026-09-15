# FAILURE MATRIX

Every major failure mode: detection, retry policy, fallback, escalation, resume point.

| Failure | Detection | Retry? | Fallback? | Escalate? | Resume Point |
|---------|-----------|--------|-----------|-----------|--------------|
| Gemini 429 RATE_LIMIT | HTTP 429 / RESOURCE_EXHAUSTED | Yes — backoff (10s, 20s, 40s) | No | Yes, after retries exhausted | ai_planning |
| Gemini 401 AUTH | HTTP 401 / invalid key | No (non-retryable) | No | Yes — permanent, needs new key | ai_planning |
| Gemini timeout | URLError timeout | Yes — 3s backoff | No | Yes, after retries | ai_planning |
| Gemini invalid JSON | Parse error | Yes — regenerate | No | Yes, after retries | ai_planning |
| OpenAI failure | HTTP/network error | Yes (rate limit/transient only) | No | Yes | ai_planning |
| Objaverse unavailable | Network check fails | Yes — 2 attempts | Try external API | Yes if all providers fail | asset stage |
| 3D API timeout | URLError | Yes — backoff | Try objaverse | Yes if all fail | asset stage |
| TTS quota (gTTS) | HTTP error / rate limit | Yes — backoff | None (single provider) | Yes | voice_tts |
| Telegram send failure | HTTP error | Yes — 3 attempts | Log-only (delivery non-critical) | N/A | N/A |
| Blender crash | Exit code / stderr | Yes — 1 retry | No | Yes | render (failed partition only) |
| Blender OOM | Killed / OOM in stderr | Yes — reduce load | Lower samples if quality allows | Yes if repeated | render |
| EGL/OpenGL failure | stderr pattern | No — env issue | Software rendering (recorded in metrics) | Yes if render fails | render |
| Missing render frames | Collector manifest check | No (deterministic check) | Re-render missing partition only | Yes if >10% missing | render |
| Duplicate render frames | Collector manifest check | No | Deduplicate | No | render |
| FFmpeg encode failure | Exit code | Yes — 1 retry | No | Yes | ffmpeg_assembly |
| Audio merge failure | Exit code | Yes — 1 retry | NO silent fallback (v3 fix) | Yes | ffmpeg_assembly |
| QC failure | Quality check score < threshold | Yes — 1 retry with adjusted settings | No | Yes | quality_check |
| GitHub artifact missing | Download failure | Yes — 1 retry | No | Yes | depends on stage |
| Worker partition failure | Worker exit code | Yes — retry ONLY that partition | No | Yes if repeated | render (that partition) |

## Error Classification (utils/error_classifier.py)

| Class | Retryable | Examples |
|-------|-----------|----------|
| TRANSIENT | Yes | timeout, connection reset, 502/503/504 |
| RATE_LIMIT | Yes (longer backoff) | 429, quota, RESOURCE_EXHAUSTED |
| AUTH | No | 401, 403, invalid key |
| INVALID_INPUT | No | 400, malformed request |
| PROVIDER_ERROR | Yes | 500 |
| OUT_OF_MEMORY | Yes (with load reduction) | OOM, killed |
| BLENDER_ERROR | Yes (once) | blender crash, GL errors |
| FFMPEG_ERROR | Yes (once) | encode/decode failure |
| QUALITY_FAILURE | Yes (adjusted) | QC below threshold |
| HUMAN_INTERVENTION | No — escalate | requires human input |
