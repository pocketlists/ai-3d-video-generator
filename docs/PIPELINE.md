# Pipeline Documentation — AI 3D Video Generator

## Pipeline Stages

The pipeline consists of 20 stages, each implemented as a GitHub Actions job:

| # | Stage | Workflow | Depends On | Parallel |
|---|-------|----------|------------|----------|
| 1 | receive_request | 01_receive_request | — | — |
| 2 | ai_planning | 02_ai_planning | receive_request | — |
| 3 | script_breakdown | 03_script_breakdown | ai_planning | — |
| 4 | asset_collection | 04_asset_collection | script_breakdown | — |
| 5 | characters | 05_characters | script_breakdown | ✓ |
| 6 | environments | 06_environments | script_breakdown | ✓ |
| 7 | props | 07_props | script_breakdown | ✓ |
| 8 | animation | 08_animation | characters, environments, props | — |
| 9 | camera | 09_camera | environments | — |
| 10 | lighting | 10_lighting | environments | — |
| 11 | voice_tts | 11_voice_tts | script_breakdown | ✓ |
| 12 | music | 12_music | script_breakdown | ✓ |
| 13 | sfx | 13_sfx | script_breakdown | ✓ |
| 14 | lip_sync | 14_lip_sync | voice_tts, characters | — |
| 15 | blender_assembly | 15_blender_assembly | animation, camera, lighting, lip_sync | — |
| 16 | render_workers | 16_render_workers | blender_assembly | ✓ (matrix) |
| 17 | quality_check | 17_quality_check | render_workers | — |
| 18 | ffmpeg_assembly | 18_ffmpeg_assembly | quality_check, voice_tts, music, sfx | — |
| 19 | telegram_delivery | 19_telegram_delivery | ffmpeg_assembly | — |
| 20 | self_optimize | 20_self_optimize | ffmpeg_assembly | — |

## Parallel Execution Layers

The pipeline's topological execution order groups stages into layers:

1. **Layer 1:** receive_request
2. **Layer 2:** ai_planning
3. **Layer 3:** script_breakdown
4. **Layer 4:** asset_collection, characters, environments, props, voice_tts, music, sfx
5. **Layer 5:** animation, camera, lighting, lip_sync
6. **Layer 6:** blender_assembly
7. **Layer 7:** render_workers (N parallel workers)
8. **Layer 8:** quality_check
9. **Layer 9:** ffmpeg_assembly, self_optimize
10. **Layer 10:** telegram_delivery

## Artifact Flow

Each stage uploads its output as a GitHub Actions artifact. Subsequent stages download and process these artifacts:

- `pipeline-request` → Request data
- `pipeline-plan` → AI-generated video plan
- `pipeline-script-breakdown` → Detailed shot list
- `pipeline-asset-collection` → Asset manifest
- `pipeline-characters` → Character mesh data
- `pipeline-environments` → Environment mesh data
- `pipeline-props` → Prop mesh data
- `pipeline-animation` → Animation keyframes
- `pipeline-camera` → Camera paths
- `pipeline-lighting` → Lighting setup
- `pipeline-voice-tts` → Voice audio files
- `pipeline-music` → Background music
- `pipeline-sfx` → Sound effects
- `pipeline-lip-sync` → Lip-sync data
- `pipeline-blender-assembly` → Blender scene script + plan
- `pipeline-render-worker-N` → Rendered frames per worker
- `pipeline-renders-collected` → All rendered frames
- `pipeline-final-video` → Final MP4 video
- `pipeline-optimization` → Metrics and recommendations

## Self-Optimization

After each run, the optimization system:

1. Collects metrics from all stages
2. Identifies bottlenecks (slowest stages)
3. Identifies inefficiencies (high samples, slow renders)
4. Identifies repeated failures
5. Identifies wasted resources (uneven worker load, oversized textures)
6. Generates safe recommendations (never lowering quality below minimum)
7. Saves recommendations for future runs to learn from

## Failure Recovery

The system handles failures by:

- Retrying recoverable failures (exponential backoff)
- Capturing useful error logs
- Validating files before dependent stages
- Detecting missing/corrupted renders
- Verifying final video exists and has correct duration
- Continuing unaffected stages where possible
