# Repository Audit — v6.0 Master Fix + Hardening

## Verification (actually executed)

| Command | Result |
|---------|--------|
| `python -m compileall .` | PASS |
| `pytest -q` BEFORE baseline | 220 passed / 0 failed |
| `pytest -q` AFTER (final) | 226 passed / 0 failed (+6 v6 tests, 0 regressions) |
| `python scripts/validate_repo.py .` | ALL CHECKS PASSED |
| `PIPELINE_MODE=test python scripts/smoke_test.py` | ALL TESTS PASSED |
| YAML parse (pipeline.yml 21 jobs, resume.yml) | VALID |

## WORKING (verified by tests)
- 21-job pipeline, artifact contract enforced in validator AND tests
- Dynamic render matrix 1-20 workers (render_prepare + fromJSON)
- Partitioning: deterministic, no gaps/overlaps (1440/20, 1440/7, 100/3, 101/20, 100/1)
- Worker output isolation (renders/worker_N/, pipeline-render-N artifacts)
- Frame collector: missing/duplicate detection, per-frame SHA256 checksums
- Single-worker retry with attempt tracking (retry_failed_partition)
- PIPELINE_MODE production guards (no placeholders, no template LLM fallback)
- Objaverse PROVIDER_UNAVAILABLE honesty (never empty-list-on-missing-package)
- Asset router source logging (ASSET_SOURCE), license UNKNOWN honesty
- Gemini schema validation + retry, no silent fallback
- TTS: Google Cloud TTS and gTTS separate providers
- Telegram: allowed-user authorization, resume tokens, channel_post support
- Cross-run resume: resume.yml with run-id + github-token + integrity verification
- State persistence: StateManager + LocalStateStore / GitHubContentsStateStore

## FIXED in v6 (this revision)
1. Workers now persist worker_status.json (worker_id, status, frames,
   elapsed, attempt, timestamps) — real data for render_manifest.json
2. render_manifest.json extended: requested_workers, actual_workers,
   expected_frames, actual_frames, worker_status, worker_attempts, timings
   (backward-compatible: all v5 keys retained)
3. Characters now get stable character_001-style IDs (both API and fallback paths)
4. resume.yml verifies downloaded artifact integrity (SHA256 frame checksums)
5. Quality job prints worker truth: REQUESTED/ACTUAL_MATRIX/ACTIVE/COMPLETED/FAILED
6. Docs added: RENDER_WORKERS.md, OBJAVERSE.md, FINAL_PRE_REPAIR_AUDIT.md

## NOT TESTED (honest)
- REAL API tests (Gemini, Google Cloud TTS, Objaverse live, Telegram live) =
  NOT RUN — credentials unavailable. Mock-backed tests PASS.
- Real Blender render on GitHub Actions = NOT RUN (needs live runner).
- Real cross-run artifact download = NOT RUN (needs two live runs).

## KNOWN LIMITATIONS
- GitHub standard runners: CPU-only (no GPU) — Eevee renders are slow
- Objaverse is an optional dependency (`pip install objaverse`), documented in docs/OBJAVERSE.md
- blender/asset_importer.py full import requires bpy runtime
- Cross-run artifact download requires artifacts within GitHub retention window

Generated: 2026-09-16
