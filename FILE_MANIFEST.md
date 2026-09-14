# FILE_MANIFEST.md — Complete File Listing

This manifest contains every file that exists in the repository. The repository must match this manifest.

## Root Files
- `README.md`
- `FILE_MANIFEST.md`
- `REPOSITORY_AUDIT.md`
- `requirements.txt`
- `.gitignore`
- `setup.py`
- `LICENSE`

## Configuration
- `config/default.yaml`
- `config/blender_settings.yaml`
- `config/secrets_template.env`

## Controller (`controller/`)
- `controller/__init__.py`
- `controller/config_loader.py`
- `controller/state_manager.py`
- `controller/pipeline.py`
- `controller/orchestrator.py`

## Workers (`workers/`)
- `workers/__init__.py`
- `workers/base_worker.py`
- `workers/planning_worker.py`
- `workers/script_worker.py`
- `workers/asset_worker.py`
- `workers/character_worker.py`
- `workers/environment_worker.py`
- `workers/prop_worker.py`
- `workers/animation_worker.py`
- `workers/camera_worker.py`
- `workers/lighting_worker.py`
- `workers/voice_tts_worker.py`
- `workers/music_worker.py`
- `workers/sfx_worker.py`
- `workers/lip_sync_worker.py`
- `workers/blender_assembly_worker.py`
- `workers/render_worker.py`
- `workers/quality_check_worker.py`
- `workers/ffmpeg_worker.py`
- `workers/telegram_worker.py`
- `workers/optimization_worker.py`

## Utils (`utils/`)
- `utils/__init__.py`
- `utils/logger.py`
- `utils/telemetry.py`
- `utils/file_validator.py`
- `utils/artifact_store.py`
- `utils/retry.py`
- `utils/telegram_client.py`

## Blender (`blender/`)
- `blender/__init__.py`
- `blender/low_poly_generator.py`
- `blender/scene_builder.py`
- `blender/render_manager.py`
- `blender/optimization.py`

## Optimizer (`optimizer/`)
- `optimizer/__init__.py`
- `optimizer/metrics_collector.py`
- `optimizer/analyzer.py`
- `optimizer/rules.py`

## Tests (`tests/`)
- `tests/__init__.py`
- `tests/test_config.py`
- `tests/test_file_validation.py`
- `tests/test_workflow_logic.py`
- `tests/test_asset_handling.py`
- `tests/test_scene_generation.py`
- `tests/test_render_preparation.py`
- `tests/test_ffmpeg_assembly.py`
- `tests/test_telegram_upload.py`
- `tests/test_optimization.py`
- `tests/test_failure_recovery.py`

## Scripts (`scripts/`)
- `scripts/smoke_test.py`
- `scripts/install_blender.py`
- `scripts/validate_repo.py`

## Documentation (`docs/`)
- `docs/ARCHITECTURE.md`
- `docs/SETUP.md`
- `docs/SECRETS.md`
- `docs/PIPELINE.md`

## GitHub Actions Workflows (`.github/workflows/`)
- `.github/workflows/01_receive_request.yml`
- `.github/workflows/02_ai_planning.yml`
- `.github/workflows/03_script_breakdown.yml`
- `.github/workflows/04_asset_collection.yml`
- `.github/workflows/05_characters.yml`
- `.github/workflows/06_environments.yml`
- `.github/workflows/07_props.yml`
- `.github/workflows/08_animation.yml`
- `.github/workflows/09_camera.yml`
- `.github/workflows/10_lighting.yml`
- `.github/workflows/11_voice_tts.yml`
- `.github/workflows/12_music.yml`
- `.github/workflows/13_sfx.yml`
- `.github/workflows/14_lip_sync.yml`
- `.github/workflows/15_blender_assembly.yml`
- `.github/workflows/16_render_workers.yml`
- `.github/workflows/17_quality_check.yml`
- `.github/workflows/18_ffmpeg_assembly.yml`
- `.github/workflows/19_telegram_delivery.yml`
- `.github/workflows/20_self_optimize.yml`

## Summary

| Category | Count |
|----------|-------|
| Root files | 7 |
| Config files | 3 |
| Controller modules | 5 |
| Worker modules | 21 |
| Utils modules | 7 |
| Blender modules | 5 |
| Optimizer modules | 4 |
| Test files | 12 |
| Scripts | 3 |
| Documentation | 4 |
| GitHub Actions workflows | 20 |
| **Total** | **91** |
