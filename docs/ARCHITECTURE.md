# Architecture — AI 3D Video Generator

## Overview

The AI 3D Video Generator is a production-grade system that generates approximately 1-minute low-poly 3D videos automatically through GitHub Actions. It uses a 20-stage pipeline with parallel execution, self-optimization, and Telegram delivery.

## Pipeline Architecture

```
Request → Planning → Script → Assets → {Characters | Environments | Props}
                                              ↓
                              Animation ← (characters, env, props)
                              Camera ← (environments)
                              Lighting ← (environments)
                              Voice/TTS ← (script)    Music ← (script)    SFX ← (script)
                                          ↓
                              Lip-Sync ← (voice, characters)
                                          ↓
                              Blender Assembly ← (animation, camera, lighting, lip-sync)
                                          ↓
                              Render Workers (N parallel) ← (blender_assembly)
                                          ↓
                              Quality Check ← (renders)
                                          ↓
                              FFmpeg Assembly ← (quality, voice, music, sfx)
                                          ↓                              ↓
                              Telegram Delivery          Self-Optimize
```

## Design Principles

### 1. Parallel Execution
Independent stages (characters, environments, props, voice, music, SFX) run in parallel. Only dependent stages wait.

### 2. Distributed Rendering
The render stage uses a GitHub Actions matrix to run N workers in parallel, each rendering a subset of frames.

### 3. Self-Learning Optimization
After every run, metrics are collected and analyzed. The system learns from past runs to optimize future settings without lowering quality below minimum thresholds.

### 4. Failure Recovery
Each stage has retry logic, error capture, and the ability to continue unaffected stages when possible.

### 5. No File Skipping
Every file in the manifest is implemented. No placeholders, no TODOs.

## Repository Structure

```
├── .github/workflows/     # 20 GitHub Actions workflows
├── controller/            # Pipeline orchestration
├── workers/               # 20 stage workers
├── blender/               # 3D scene building and rendering
├── optimizer/             # Self-learning optimization
├── utils/                 # Shared utilities (logging, telemetry, etc.)
├── config/                # YAML configuration
├── tests/                 # Test suite
├── scripts/               # Smoke test, validation, installation
├── docs/                  # Documentation
├── FILE_MANIFEST.md       # Complete file listing
└── REPOSITORY_AUDIT.md    # Audit report
```

## Data Flow

1. Artifacts are passed between GitHub Actions jobs via `upload-artifact` / `download-artifact`
2. State is managed via JSON files in the artifact directory
3. Metrics are stored in a separate metrics directory for optimization
4. No assumption is made about permanent storage on GitHub-hosted runners

## Quality Guarantees

- Minimum render samples: 32 (never lowered automatically)
- Minimum resolution: 960×540
- Minimum FPS: 24
- Target duration: ~60 seconds
