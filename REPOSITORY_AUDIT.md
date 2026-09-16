# Repository Audit — v5.0 Safe-Fix

## Verification (actually executed)

| Command | Result |
|---------|--------|
| `python -m compileall .` | PASS |
| `pytest -q` | 220 passed, 0 failed (210 before + 10 new v5 tests) |
| `python scripts/validate_repo.py .` | ALL CHECKS PASSED (upgraded validator: 12 check groups) |
| `python scripts/smoke_test.py` (PIPELINE_MODE=test) | see smoke output |
| YAML parse (pipeline.yml, resume.yml) | VALID (21 jobs + 1 job) |

## WORKING (verified by tests)
- Pipeline: 21 jobs, 19 uploads all with name+path, 28 downloads all with name/pattern
- Dynamic render matrix: render_prepare + fromJSON, 1-20 workers (tested 1/2/4/7/20, 101/20)
- Partitioning: deterministic, no gaps/overlaps, single-worker and uneven cases tested
- Worker retry: single failed worker retried, attempt tracked
- Frame collector: missing/duplicate/corrupt frame detection, render_manifest.json
- Cross-run resume: GitHubContentsStateStore + resume.yml with run-id + github-token
- Telegram: allowed-user validation, resume token, WAITING_FOR_USER, channel_post support
- Objaverse: PROVIDER_UNAVAILABLE honesty, cache, license metadata
- Gemini: PIPELINE_MODE gate, schema validation, retry on malformed JSON
- TTS: Google Cloud TTS and gTTS separate providers, both preserved
- Optimizer: bounded, quality-aware, no quality destruction
- Security: no secrets in repo (validator scan), no script injection in resume.yml

## FIXED in v5 (this revision)
1. resume.yml: continue-on-error removed from artifact download; cross-run download
   now uses the supported run-id + github-token mechanism
2. resume.yml: final upload-artifact now has name + path
3. resume.yml: stage passed via env var (no command injection via inputs)
4. pipeline.yml: Blender install no longer uses `|| true`; explicit
   `blender --version` verification step added
5. validate_repo.py: now checks ast.ImportFrom, artifact upload name/path,
   download name/pattern, producer/consumer consistency, error-swallowing
   (`|| true`, `except: pass`), hard-coded render matrix

## NOT TESTED (honest)
- Real Gemini API calls (no credentials) — interface tested with mocks
- Real Google Cloud TTS (no credentials) — gTTS path tested with mocks
- Real Objaverse downloads (network/optional package) — mocked in tests
- Real Blender render on GitHub Actions (requires live runner)
- Real Telegram delivery (requires bot token)

## KNOWN LIMITATIONS
- GitHub standard runners are CPU-only; Eevee renders are slow
- blender/asset_importer.py full import path requires bpy (Blender runtime)
- Cross-run artifact download requires the original run's artifacts to still
  exist within GitHub's retention window

Generated: 2026-09-16
