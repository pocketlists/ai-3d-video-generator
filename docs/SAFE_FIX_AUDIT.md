# Safe-Fix Audit (v5)

## Method
Fresh clone of `main` (commit dc749948), full inspection before any change.
Baseline: `compileall` OK, `pytest -q` = 210 passed / 0 failed.

## Working (verified — DO NOT change)
- 21-job pipeline.yml: all 19 uploads have name+path, all 28 downloads have name/pattern
- Dynamic render matrix (render_prepare + fromJSON), 1-20 workers
- Partition logic: deterministic, no gaps/overlaps (tested 1/2/4/7/20 workers, 100/3 uneven)
- Worker retry (single worker, attempt tracking), frame collector validation
- render_manifest.json with checksums
- Objaverse PROVIDER_UNAVAILABLE honesty, AssetRouter cache→objaverse→external→procedural
- Gemini PIPELINE_MODE gate (no template fallback in production)
- Google Cloud TTS separated from gTTS (both preserved)
- Telegram escalation: allowed-user validation, resume token, WAITING_FOR_USER state
- GitHubContentsStateStore (state in pipeline-state branch)
- Optimizer: bounded, quality-aware recommendations
- Error classification (utils/error_classifier.py)

## Real bugs found (this audit)
1. **resume.yml: `continue-on-error: true` on artifact download** — hides real
   failures; cross-run download by name alone does not work in Actions v4 anyway.
2. **resume.yml: final upload-artifact has EMPTY `with:`** — upload would fail or upload nothing.
3. **resume.yml: `${{ inputs.stage }}` interpolated directly into run command** — script injection risk.
4. **pipeline.yml: Blender install uses `2>/dev/null || true`** — hides installation
   errors; production render would then fail later with a confusing error instead of a clear one.
5. **scripts/validate_repo.py: only checks `ast.Import`** — misses `from x import y`
   (`ast.ImportFrom`); no artifact name/path validation, no producer/consumer
   consistency check, no error-swallowing scan.

## Repair plan (smallest safe change)
- resume.yml: use `actions/download-artifact@v4` with `run-id` + `github-token`
  (the supported cross-run mechanism), remove continue-on-error, add name+path to
  the final upload, pass stage via env var.
- pipeline.yml: remove `|| true` from Blender install, add explicit
  `blender --version` verification step.
- validate_repo.py: ADD checks (keep all existing): ImportFrom, artifact
  upload/download validation, producer/consumer consistency, `|| true` /
  `except: pass` scan.
- tests/test_v5.py: artifact contract test, 101/20 uneven partition test.

## Files that must NOT be touched
All provider implementations, workers, blender/, optimizer/, controller/, core/,
utils/, existing tests — verified working by the 210-test suite.
