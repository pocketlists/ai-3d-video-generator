# Artifact Dependency Graph

## Overview

Every stage produces an artifact that downstream stages consume. Artifact names
are deterministic and match exactly between producer and consumer.

## Artifact Flow

```
receive (pipeline-request)
  ↓
planning (pipeline-plan)
  ↓
script (pipeline-script)
  ↓
├── assets (pipeline-assets)
├── characters (pipeline-characters)
├── environments (pipeline-environments)
├── props (pipeline-props)
├── voice_tts (pipeline-voice)
├── music (pipeline-music)
└── sfx (pipeline-sfx)
    ↓
├── animation (needs: characters + environments + props) → pipeline-animation
├── camera (needs: environments) → pipeline-camera
├── lighting (needs: environments) → pipeline-lighting
└── lip_sync (needs: voice_tts + characters) → pipeline-lipsync
    ↓
assembly (needs: animation + camera + lighting + lip_sync) → pipeline-assembly
  ↓
render_prepare (needs: assembly) → outputs matrix, num_workers, total_frames
  ↓
render (needs: assembly + render_prepare, matrix) → pipeline-render-{worker_id}
  ↓
quality (needs: render, downloads pipeline-render-*) → pipeline-quality
  ↓
ffmpeg (needs: quality + voice_tts + music + sfx) → pipeline-final
  ↓
├── delivery (needs: ffmpeg, downloads pipeline-final) → sends via Telegram
└── optimize (needs: ffmpeg, downloads pipeline-quality) → pipeline-optimization
```

## Artifact Registry

| Artifact Name | Producer | Consumer(s) | Path | Format | Retention |
|---------------|----------|-------------|------|--------|-----------|
| pipeline-request | receive | planning | /tmp/pipeline_artifacts/ | JSON | 7 days |
| pipeline-plan | planning | script | /tmp/pipeline_artifacts/ | JSON | 7 days |
| pipeline-script | script | assets, characters, environments, props, voice_tts, music, sfx | /tmp/pipeline_artifacts/ | JSON | 7 days |
| pipeline-assets | assets | (consumed by assembly indirectly) | /tmp/pipeline_artifacts/ | JSON | 7 days |
| pipeline-characters | characters | animation, lip_sync | /tmp/pipeline_artifacts/ | JSON | 7 days |
| pipeline-environments | environments | animation, camera, lighting | /tmp/pipeline_artifacts/ | JSON | 7 days |
| pipeline-props | props | animation | /tmp/pipeline_artifacts/ | JSON | 7 days |
| pipeline-voice | voice_tts | lip_sync, ffmpeg | /tmp/pipeline_artifacts/ | Audio | 7 days |
| pipeline-music | music | ffmpeg | /tmp/pipeline_artifacts/ | Audio | 7 days |
| pipeline-sfx | sfx | ffmpeg | /tmp/pipeline_artifacts/ | Audio | 7 days |
| pipeline-animation | animation | assembly | /tmp/pipeline_artifacts/ | JSON | 7 days |
| pipeline-camera | camera | assembly | /tmp/pipeline_artifacts/ | JSON | 7 days |
| pipeline-lighting | lighting | assembly | /tmp/pipeline_artifacts/ | JSON | 7 days |
| pipeline-lipsync | lip_sync | assembly | /tmp/pipeline_artifacts/ | JSON | 7 days |
| pipeline-assembly | assembly | render_prepare, render | /tmp/pipeline_artifacts/ | .blend | 7 days |
| pipeline-render-{id} | render (per worker) | quality | /tmp/pipeline_artifacts/renders/worker_{id}/ | PNG frames | 7 days |
| pipeline-quality | quality | ffmpeg, optimize | /tmp/pipeline_artifacts/ | JSON | 7 days |
| pipeline-final | ffmpeg | delivery | /tmp/pipeline_artifacts/output/ | MP4 | 14 days |
| pipeline-optimization | optimize | (terminal) | /tmp/pipeline_metrics/ | JSON | 30 days |

## Cross-Run Artifact Access

GitHub Actions `actions/download-artifact@v4` can only download artifacts from
the **same workflow run**. For cross-run resume:

1. **State**: persisted via `GitHubContentsStateStore` (commits to `pipeline-state` branch)
2. **Artifacts**: the resume workflow re-runs the failed stage, which regenerates
   its own artifacts. Completed stages are NOT re-run (checkpoint verified),
   so their artifacts from the original run are not needed.
3. **job_id**: passed as a resume.yml input, validated against the stored state.

## Validation

The pipeline validator (`scripts/validate_repo.py`) checks that every
`upload-artifact` step has a `name` and `path`, and every `download-artifact`
step has a `name` or `pattern`. Empty `with:` blocks are flagged as errors.
