# Resume Architecture

## Overview

The pipeline is resumable across GitHub Actions runs. When a critical provider
fails (e.g., Gemini 429), the job is NOT lost:

```
Provider failure
  → retry (classified: TRANSIENT/RATE_LIMIT retry with backoff)
  → checkpoint saved (atomic write)
  → Telegram escalation (JOB_ID, STAGE, PROVIDER, ERROR, RESUME_TOKEN)
  → state = WAITING_FOR_EXTERNAL_RESPONSE
  → runner EXITS cleanly (no waiting — a runner is never held alive)
  → [minutes/hours/days later] authorized Telegram reply
  → resume.yml workflow_dispatch (or manual)
  → validate job_id + resume_token
  → load persistent checkpoint (core/storage.py)
  → store external response
  → resume EXACT failed stage (completed stages never re-run)
```

## Job Identity

Every request gets `job_id = job_YYYYMMDD_HHMMSS_<6-hex>` (created in the
receive job). All checkpoints, artifacts, logs, and Telegram messages carry
this job_id. `workflow_run_id` is recorded but is NOT the identity — resume
runs happen in different workflow runs.

## State Backends (config: STATE_BACKEND)

| Backend | Class | Persistence | Use |
|---------|-------|-------------|-----|
| local | LocalStateStore | runner disk only | local dev, tests |
| artifact | GitHubArtifactStateStore | Actions artifacts (7-30 day retention) | in-run + short resume |
| repository | GitHubRepositoryStateStore | local file (documented limitation) | legacy |
| contents | GitHubContentsStateStore | **real** — commits state JSON via `gh api` PUT /contents | production cross-run |

The `contents` backend commits `state/<job_id>.json` to the `pipeline-state`
branch via the GitHub Contents API — state survives runner destruction
indefinitely (as long as the branch exists).

## Checkpoints (controller/checkpoint.py)

Every stage writes `checkpoint_<job_id>_<stage>.json` atomically
(temp file → fsync → rename). A corrupted checkpoint returns None on load —
it never destroys the previously valid one.

## Resume Rules

- Resume point = first stage without a `completed` checkpoint.
- Completed stages are NEVER re-run (verified by
  `tests/test_v4.py::TestStatePersistence` and `TestTelegramResumeFlow`).
- Stage output hashes enable reuse: if a stage's input hash is unchanged,
  its previous output is reused.

## How to Resume

1. From the escalation Telegram message, note JOB_ID, STAGE, RESUME_TOKEN.
2. Actions → "Resume Pipeline" → Run workflow with those three inputs +
   your response (JSON plan or instruction).
3. The workflow validates the token, loads the checkpoint, and runs the
   exact failed stage with the external response.
