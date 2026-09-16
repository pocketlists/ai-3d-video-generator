# Artifact Contract

Machine-verifiable contract between pipeline stages. Enforced by
`scripts/validate_repo.py` and `tests/test_v5.py`.

## Rules

1. Every `upload-artifact@v4` MUST have non-empty `name` and `path`.
2. Every `download-artifact@v4` MUST have non-empty `name` or `pattern`.
3. A download referencing a literal name must be produced by an upload in the
   same workflow (cross-run resume downloads are exempt — they use `run-id`).
4. Upload `name` values must be unique per workflow run.
5. The render matrix must be dynamic (`fromJSON(needs.render_prepare.outputs.matrix)`).

## Stage contract

| Stage | Consumes | Produces |
|-------|----------|----------|
| receive | — | `pipeline-request` (request.json) |
| planning | `pipeline-request` | `pipeline-plan` (plan.json) |
| script | `pipeline-plan` | `pipeline-script` (script.json) |
| assets | `pipeline-script` | `pipeline-assets` |
| characters | `pipeline-script` | `pipeline-characters` |
| environments | `pipeline-script` | `pipeline-environments` |
| props | `pipeline-script` | `pipeline-props` |
| voice_tts | `pipeline-script` | `pipeline-voice` (audio) |
| music | `pipeline-script` | `pipeline-music` (audio) |
| sfx | `pipeline-script` | `pipeline-sfx` (audio) |
| animation | `pipeline-characters`, `pipeline-environments`, `pipeline-props` | `pipeline-animation` |
| camera | `pipeline-environments` | `pipeline-camera` |
| lighting | `pipeline-environments` | `pipeline-lighting` |
| lip_sync | `pipeline-voice`, `pipeline-characters` | `pipeline-lipsync` |
| assembly | `pipeline-animation`, `pipeline-camera`, `pipeline-lighting`, `pipeline-lipsync` | `pipeline-assembly` (.blend) |
| render_prepare | `pipeline-assembly` | outputs: matrix, num_workers, total_frames |
| render (matrix) | `pipeline-assembly` | `pipeline-render-{worker_id}` (frames) |
| quality | `pipeline-render-*` (pattern) | `pipeline-quality` |
| ffmpeg | `pipeline-quality`, `pipeline-voice`, `pipeline-music`, `pipeline-sfx` | `pipeline-final` (mp4) |
| delivery | `pipeline-final` | — (Telegram) |
| optimize | `pipeline-quality` | `pipeline-optimization` (metrics) |
| resume (cross-run) | `pipeline-{stage}` via `run-id` when provided | `pipeline-{stage}-resume-{job_id}` |
