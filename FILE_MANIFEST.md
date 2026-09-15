# FILE_MANIFEST.md (v3.0)

*Regenerated from the actual v3.0 build — status is verified, not claimed.*

## Status Legend
- IMPLEMENTED — code complete, locally verified
- PROVIDER_DEPENDENT — interface complete; requires external credentials/service
- TEST_ONLY — used exclusively by tests
- OPTIONAL — fallback/dev convenience only

## Root
| File | Purpose | Status |
|------|---------|--------|
| README.md | Honest project overview | IMPLEMENTED |
| FILE_MANIFEST.md | This file | IMPLEMENTED |
| REPOSITORY_AUDIT.md | Final audit with measured results | IMPLEMENTED |
| requirements.txt | Dependencies | IMPLEMENTED |
| setup.py | Package setup | IMPLEMENTED |
| LICENSE | MIT license | IMPLEMENTED |
| .gitignore | Git ignore rules | IMPLEMENTED |

## .github/workflows
| File | Purpose | Status |
|------|---------|--------|
| pipeline.yml | **Master pipeline** — all 20 stages as jobs with needs: + artifacts | IMPLEMENTED |
| resume.yml | **Resume workflow** — external response resume with token validation | IMPLEMENTED |
| 01-20_*.yml (legacy) | v2.0 per-stage workflows (superseded by pipeline.yml) | OPTIONAL |

## core/
| File | Purpose | Status |
|------|---------|--------|
| __init__.py | Package init | IMPLEMENTED |
| storage.py | State storage abstraction (Local/Artifact/Repository) | IMPLEMENTED |

## controller/
| File | Purpose | Status |
|------|---------|--------|
| __init__.py | Package init | IMPLEMENTED |
| orchestrator.py | Stage runner CLI | IMPLEMENTED |
| pipeline.py | Stage DAG definition | IMPLEMENTED |
| config_loader.py | Config loading | IMPLEMENTED |
| state_manager.py | **State machine with transitions, checkpoints, resume** | IMPLEMENTED |
| hermes.py | **Agent orchestration — decisions, retry, escalate, resume** | IMPLEMENTED |
| telegram_escalation.py | **Escalation with resume tokens — no timeout, runner exits** | IMPLEMENTED |
| checkpoint.py | **Atomic checkpoint system** | IMPLEMENTED |

## providers/
| File | Purpose | Status |
|------|---------|--------|
| __init__.py | Package init | IMPLEMENTED |
| llm_provider.py | **Gemini/OpenAI/Template — no silent fallback, style-aware** | IMPLEMENTED (Gemini/OpenAI PROVIDER_DEPENDENT) |
| asset_provider.py | Generic 3D API provider + cache | IMPLEMENTED (PROVIDER_DEPENDENT) |
| objaverse_provider.py | **Objaverse-XL retrieval — search/rank/download** | PROVIDER_DEPENDENT |
| asset_router.py | **Routing: cache → objaverse → external API** | IMPLEMENTED |
| tts_provider.py | TTS abstraction (gTTS/espeak) | IMPLEMENTED (free tier limits) |
| audio_provider.py | Music + SFX providers | IMPLEMENTED |
| lip_sync_provider.py | Lip-sync abstraction | IMPLEMENTED |

## workers/ (21 files)
| File | Purpose | Status |
|------|---------|--------|
| base_worker.py | Base class | IMPLEMENTED |
| planning_worker.py | Planning via LLM provider | IMPLEMENTED |
| script_worker.py | Script breakdown | IMPLEMENTED |
| asset_worker.py | Asset collection manifest | IMPLEMENTED |
| character/environment/prop_worker.py | Asset-based generation with fallback | IMPLEMENTED |
| animation/camera/lighting_worker.py | Scene components | IMPLEMENTED |
| voice_tts_worker.py | TTS via provider | IMPLEMENTED |
| music/sfx_worker.py | Audio generation | IMPLEMENTED |
| lip_sync_worker.py | Lip sync | IMPLEMENTED |
| blender_assembly_worker.py | Scene assembly | IMPLEMENTED |
| render_worker.py | **Rendering with CPU monitoring, per-worker output** | IMPLEMENTED |
| quality_check_worker.py | QC | IMPLEMENTED |
| ffmpeg_worker.py | **Final encode — no silent fallback, structured errors** | IMPLEMENTED |
| telegram_worker.py | Delivery | IMPLEMENTED |
| optimization_worker.py | Self-optimize | IMPLEMENTED |

## blender/
| File | Purpose | Status |
|------|---------|--------|
| __init__.py | Package init | IMPLEMENTED |
| low_poly_generator.py | Procedural meshes | OPTIONAL (smoke test/fallback only) |
| scene_builder.py | Scene building | IMPLEMENTED |
| render_manager.py | **Deterministic partitioning, version-aware engine, collector fix** | IMPLEMENTED |
| optimization.py | Render optimization | IMPLEMENTED |

## optimizer/
| File | Purpose | Status |
|------|---------|--------|
| __init__.py, metrics_collector.py, analyzer.py, rules.py | Quality-aware optimization | IMPLEMENTED |

## utils/
| File | Purpose | Status |
|------|---------|--------|
| __init__.py | Package init | IMPLEMENTED |
| logger.py | Structured logging | IMPLEMENTED |
| telemetry.py | Telemetry | IMPLEMENTED |
| file_validator.py | File validation | IMPLEMENTED |
| artifact_store.py | Artifact tracking | IMPLEMENTED |
| retry.py | Retry with backoff | IMPLEMENTED |
| telegram_client.py | Telegram client | IMPLEMENTED |
| cpu_monitor.py | **Real CPU/RAM measurements** | IMPLEMENTED |
| asset_validator.py | GLB/GLTF/FBX/OBJ validation | IMPLEMENTED |
| error_classifier.py | **Error classification for retry/escalation** | IMPLEMENTED |

## tests/
| File | Purpose | Status |
|------|---------|--------|
| mocks.py | **Mock providers — no paid APIs needed** | TEST_ONLY |
| test_v3.py | **v3.0 regression tests (35+ tests)** | TEST_ONLY |
| test_providers.py | Provider tests | TEST_ONLY |
| test_hermes.py | Hermes/escalation tests | TEST_ONLY |
| test_config.py, test_file_validation.py, etc. | v2.0 tests (preserved) | TEST_ONLY |

## scripts/
| File | Purpose | Status |
|------|---------|--------|
| smoke_test.py | **10-check end-to-end smoke test** | IMPLEMENTED |
| validate_repo.py | **Deep validation — syntax/YAML/secrets/imports/TODO** | IMPLEMENTED |
| install_blender.py | Blender installer | IMPLEMENTED |

## config/
| File | Purpose | Status |
|------|---------|--------|
| default.yaml | **v3.0 config — no secrets, quality classes, profiles** | IMPLEMENTED |
| blender_settings.yaml | Blender settings | IMPLEMENTED |
| secrets_template.env | **Updated template with all v3.0 vars** | IMPLEMENTED |

## docs/
| File | Purpose | Status |
|------|---------|--------|
| INITIAL_AUDIT.md | **v2.0 bugs found before v3.0 (PHASE 0)** | IMPLEMENTED |
| FAILURE_MATRIX.md | **Every failure: detection/retry/escalation/resume** | IMPLEMENTED |
| ARCHITECTURE.md, SETUP.md, SECRETS.md, PIPELINE.md | Existing docs (preserved) | IMPLEMENTED |
