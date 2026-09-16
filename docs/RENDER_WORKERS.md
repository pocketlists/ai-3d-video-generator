# Render Workers

## Worker count (dynamic)
The `render_prepare` job converts the `num_workers` input (1-20) into a JSON
matrix: `[0, 1, ..., N-1]`. The render job uses
`matrix: worker_id: ${{ fromJSON(needs.render_prepare.outputs.matrix) }}`,
so any count from 1 to 20 runs without YAML edits. Requested counts above 20
are clamped to 20 and the clamp is logged (`REQUESTED_WORKERS` vs
`MATRIX_WORKERS`).

## Worker truth reporting
Each worker writes `worker_status.json` into its own output directory with
`worker_id`, `status`, `frames_rendered`, `elapsed_sec`, `attempt`,
`started_at`, `ended_at`, `error`. The frame collector merges these into
`render_manifest.json` (`worker_status`, `worker_attempts`, `timings`,
`requested_workers`, `actual_workers`). The quality job prints
REQUESTED/ACTUAL_MATRIX/ACTIVE/COMPLETED/FAILED workers from the manifest —
never a claimed count that did not run. Unknown values stay `null`/`unknown`.

## Partitioning
`RenderManager.partition_frames(total_frames, num_workers)` is deterministic:
worker 0 starts at frame 1, the last worker ends at `total_frames`, adjacent
ranges are contiguous (no gaps, no overlaps). Uneven counts distribute
deterministically. Tested: 1440/20, 1440/7, 100/3, 101/20, 100/1.

## Output isolation
Each worker renders only into `renders/worker_<id>/` and uploads artifact
`pipeline-render-<id>` — no worker can overwrite another.

## Production safety
`PIPELINE_MODE=production` + missing `.blend` → the worker FAILS (RuntimeError),
never placeholder frames. Placeholders exist only in `PIPELINE_MODE=test`.

## Failed worker retry
`retry_failed_partition(worker_id)` re-renders only the failed worker's
partition. Attempt numbers are recorded in `worker_status.json`
(`RENDER_ATTEMPT` env var) and the manifest.
