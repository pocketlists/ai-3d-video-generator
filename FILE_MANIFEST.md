# FILE_MANIFEST.md (v4.0)

*Regenerated from the actual filesystem after v4.0 hardening.*

## Status Legend
- IMPLEMENTED — code complete, locally verified by tests
- PROVIDER_DEPENDENT — interface complete; requires external credentials/service
- TEST_ONLY — used exclusively by tests
- OPTIONAL — fallback/dev convenience only

## Root
| File | Purpose | Status |
|------|---------|--------|
| README.md | Honest project overview | IMPLEMENTED |
| FILE_MANIFEST.md | This file (auto-generated) | IMPLEMENTED |
| REPOSITORY_AUDIT.md | Final audit with measured results | IMPLEMENTED |
| requirements.txt | Dependencies | IMPLEMENTED |
| setup.py | Package setup (v4.0.0) | IMPLEMENTED |
| LICENSE | MIT | IMPLEMENTED |
| .gitignore | Git ignore rules | IMPLEMENTED |

## .github/workflows
| File | Purpose | Status |
|------|---------|--------|
| pipeline.yml | **Master pipeline** — all stages as jobs, needs:, dynamic render matrix | IMPLEMENTED |
| resume.yml | **Resume workflow** — token-validated external response resume | IMPLEMENTED |

*(20 legacy per-stage workflows deleted in v4 — their functionality is fully
covered by pipeline.yml jobs with correct in-run artifacts; the 18 that chained
via `gh workflow run` were broken by design — cross-run artifacts don't resolve.)*

## core/
| File | Purpose | Status |
|------|---------|--------|
| __init__.py | Package init | IMPLEMENTED |
| storage.py | State storage: Local / Artifact / Repository / **Contents (gh api)** | IMPLEMENTED |

## controller/
| File | Purpose | Status |
|------|---------|--------|
| __init__.py | Package init | IMPLEMENTED |
| orchestrator.py | Stage runner CLI | IMPLEMENTED |
| pipeline.py | Stage DAG | IMPLEMENTED |
| config_loader.py | Config loading | IMPLEMENTED |
| state_manager.py | State machine + transitions + resume | IMPLEMENTED |
| hermes.py | Agent orchestration (decisions, retry, escalate) | IMPLEMENTED |
| telegram_escalation.py | Escalation w/ resume token, no timeout, runner exits | IMPLEMENTED |
| checkpoint.py | Atomic checkpoints | IMPLEMENTED |

## providers/
| File | Purpose | Status |
|------|---------|--------|
| __init__.py | Package init | IMPLEMENTED |
| llm_provider.py | Gemini/OpenAI/Template — no silent fallback, PIPELINE_MODE gated | IMPLEMENTED (Gemini/OpenAI PROVIDER_DEPENDENT) |
| asset_provider.py | External 3D API adapter + cache | PROVIDER_DEPENDENT |
| objaverse_provider.py | Objaverse retrieval — honest PROVIDER_UNAVAILABLE | PROVIDER_DEPENDENT |
| asset_router.py | Routing: cache → objaverse → external → (procedural: test only) | IMPLEMENTED |
| tts_provider.py | TTS abstraction (gTTS/espeak) | IMPLEMENTED |
| google_cloud_tts.py | **Google Cloud TTS (separate from gTTS)** | PROVIDER_DEPENDENT |
| audio_provider.py | Music + SFX | IMPLEMENTED |
| lip_sync_provider.py | Lip-sync (simple viseme, honestly marked) | IMPLEMENTED |

## blender/
| File | Purpose | Status |
|------|---------|--------|
| __init__.py | Package init | IMPLEMENTED |
| low_poly_generator.py | Procedural meshes — **PIPELINE_MODE gated (prod: error)** | TEST_ONLY/OPTIONAL |
| scene_builder.py | Scene building | IMPLEMENTED |
| render_manager.py | Partitioning, version-aware engine, collector + checksums | IMPLEMENTED |
| asset_importer.py | **NEW v4: GLB/GLTF/OBJ/FBX import + validation** | IMPLEMENTED |
| optimization.py | Render optimization | IMPLEMENTED |

## workers/ (21 files)
All stage workers IMPLEMENTED. render_worker.py has **PIPELINE_MODE guard
(production: no placeholder frames)**. ffmpeg_worker.py raises structured
FFmpegError (no silent fallback).

## optimizer/
analyzer.py, metrics_collector.py, rules.py — quality-aware rule-based
optimization (not claimed as ML). IMPLEMENTED.

## utils/
logger, telemetry, file_validator, artifact_store, retry, telegram_client,
cpu_monitor (real measurements), asset_validator,
**error_classifier.py (13 error classes)**. IMPLEMENTED.

## tests/ (15 files)
- conftest.py — PIPELINE_MODE=test for the suite
- mocks.py — Mock providers (never in production)
- test_v3.py, test_v4.py — 60+ regression tests (state machine, checkpoint,
  resume, partition/matrix match, production guards, asset importer,
  checksums, Telegram flow, TTS separation)
- 10 preserved v1/v2 test modules
- TEST_ONLY

## scripts/
- smoke_test.py — 10 end-to-end checks. IMPLEMENTED
- validate_repo.py — deep validation. IMPLEMENTED
- install_blender.py — Blender installer. IMPLEMENTED

## config/
- default.yaml — v4 config incl. pipeline_mode, quality tiers, profiles. IMPLEMENTED
- blender_settings.yaml, secrets_template.env (PIPELINE_MODE added). IMPLEMENTED

## docs/
ARCHITECTURE, PIPELINE, SETUP, SECRETS, FAILURE_MATRIX, INITIAL_AUDIT +
**NEW v4: RESUME, RENDERING, ASSETS, TELEGRAM, PROVIDERS**. All IMPLEMENTED.
