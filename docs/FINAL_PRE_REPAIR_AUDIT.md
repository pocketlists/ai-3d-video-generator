# Final Pre-Repair Audit (v6)

## Existing architecture (preserved)
Telegram → Controller (Hermes orchestrator) → Planning (Gemini/template) →
Script → Assets (router: cache/objaverse/external) → Characters/Environments/
Props → Voice (Google Cloud TTS / gTTS) / Music / SFX → Animation → Camera →
Lighting → Lip Sync → Assembly (Blender) → render_prepare (matrix) → Render
(matrix 1-20 workers) → Quality → FFmpeg → Delivery (Telegram) + Optimization.
State: state_manager + checkpoints + GitHubContentsStateStore (pipeline-state
branch). Resume: resume.yml with cross-run `run-id` + `github-token` download.

## Working features (verified — must not change)
- 21-job pipeline, artifact contract enforced (uploads name+path, downloads name/pattern)
- Dynamic matrix 1-20, partitioning (no gaps/overlaps), worker output isolation
- Frame collector: missing/duplicate detection, per-frame SHA256 checksums
- Single-worker retry with attempt tracking
- PIPELINE_MODE production guards (no placeholder frames / template LLM in production)
- Objaverse PROVIDER_UNAVAILABLE honesty; asset router source logging
- Gemini schema validation + retry; TTS provider separation
- Telegram allowed-user authorization, resume tokens
- Validator: syntax, Import+ImportFrom, artifact blocks, producer/consumer,
  error swallowing, matrix check
- Test suite: 220 passed / 0 failed (baseline before v6 changes)

## Gaps found (v6 scope)
1. Workers did not persist per-worker status/timing/attempt — manifest could
   not report worker truth (REQUESTED vs ACTUAL vs COMPLETED vs FAILED).
2. render_manifest.json lacked requested_workers/actual_workers/expected_frames/
   actual_frames/worker_status/worker_attempts/timings.
3. Characters had no stable character_id (character_001) — consistency risk.
4. Cross-run artifact download did not verify integrity after restore.
5. Docs RENDER_WORKERS.md / OBJAVERSE.md did not exist.

## Files involved
workers/render_worker.py, blender/render_manager.py, workers/character_worker.py,
.github/workflows/pipeline.yml, .github/workflows/resume.yml, docs/, tests/test_v6.py

## Must NOT be changed unnecessarily
All providers, controller/, core/, blender/scene_builder.py, asset_importer.py,
optimizer/, utils/, existing tests, config keys, artifact names.
