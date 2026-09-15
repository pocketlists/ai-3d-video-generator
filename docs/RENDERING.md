# Rendering Architecture

## Dynamic Worker Partitioning (PHASE 32-34)

The render matrix is generated dynamically — never hard-coded:

1. `render_prepare` job reads `num_workers` input → computes
   `matrix = [0..N-1]` (capped at 20) → outputs as JSON.
2. `render` job uses `matrix: ${{ fromJSON(needs.render_prepare.outputs.matrix) }}`.
3. Frame partitions come from the SAME worker count:
   `RenderManager.partition_frames(total_frames, num_workers)`.

Verified by `tests/test_v4.py::TestPartitionMatchesMatrix` —
matrix count == partition count, all frames covered exactly once, for
1, 2, 4, 7, and 20 workers.

## Requested vs Actual Workers

`MAX_RENDER_WORKERS=20` means UP TO 20. The manifest records
`requested_workers`, and the actual matrix length is the truth. Final
delivery reports ACTUAL workers (never claims 20 if 4 ran).

## Worker Output Isolation

Each worker renders ONLY to `renders/worker_<id>/`. The collector never
moves frames between directories — worker ownership is preserved and
recorded in `render_manifest.json`:

```json
{
  "job_id": "...",
  "total_frames": 1440,
  "workers": 4,
  "frames": {"1": "worker_0/frame_0001.png", ...},
  "checksums": {"1": "sha256-16", ...},
  "worker_ranges": {"worker_0": {"min": 1, "max": 360, "count": 360}, ...},
  "duplicates": [], "missing_frames": [], "complete": true
}
```

Per-frame sha256 checksums (first 16 hex) detect corruption and enable
hash-based reuse (no unnecessary re-render when scene unchanged).

## Failure Handling (PHASE 35)

If worker 7 fails, ONLY worker 7's partition is retried
(`RenderManager.retry_failed_partition`). Workers 0-6 are never re-rendered.
After retry exhaustion: escalation.

## Placeholder Frame Protection (PHASE 38)

`PIPELINE_MODE=production` + missing blend file → job FAILS with a clear
error. Placeholder frames are generated ONLY in `PIPELINE_MODE=test`
(verified by `TestProductionModeGuards.test_render_worker_placeholder_blocked_in_production`).

## Version-Aware Blender (PHASE 28)

`RenderManager.detect_blender_version()` reads `blender --version` and
resolves the engine: Blender ≥ 4.2 → `BLENDER_EEVEE_NEXT`, older →
`BLENDER_EEVEE`.

## Quality Profiles

draft / standard / high / ultra (config/default.yaml `quality_profiles`) —
samples and resolution per profile. Optimizer may tune within profile limits,
never below MIN_QUALITY_SCORE.

## Known Limitations

- GitHub standard runners: CPU-only (no GPU) — Eevee on CPU is slow for
  1440 frames; expect long render jobs or reduce frames/profile.
- Actual concurrency depends on GitHub runner availability.
