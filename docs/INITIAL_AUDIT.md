# INITIAL AUDIT (v2.0 → v3.0 Upgrade)

*This audit was performed BEFORE making v3.0 changes, on commit `69a042c`.*

## Repository State Before v3.0

- Total files: 102
- Python files: 71
- Workflow files: 20
- Test modules: 13
- All files pass syntax check

## Critical Bugs Found (by actual code inspection)

### 1. WORKFLOW CHAINING BROKEN (CRITICAL)
**Files:** 18 of 20 workflows
**Bug:** Workflows chain via `gh workflow run <next>.yml` but then expect
`actions/download-artifact` to find artifacts from the *previous* workflow run.
GitHub artifacts are NOT shared across unrelated workflow runs by default.
**Impact:** Pipeline breaks at stage 2+ in real CI — artifacts from stage 1 unavailable.
**Fix (v3.0):** Single master `pipeline.yml` with job-level `needs:` — artifacts
passed between jobs in the same run.

### 2. EPHEMERAL STATE (CRITICAL)
**File:** `controller/state_manager.py` line 37
**Bug:** `DEFAULT_STATE_DIR = Path(os.environ.get("STATE_DIR", "/tmp/pipeline_state"))`
`/tmp` on GitHub runners is destroyed when the job ends. State cannot survive
across runs, making resume impossible in CI.
**Fix (v3.0):** `core/storage.py` with LocalStateStore / GitHubArtifactStateStore /
GitHubRepositoryStateStore abstraction; state uploaded as artifact.

### 3. SILENT LLM FALLBACK (CRITICAL)
**File:** `providers/llm_provider.py` lines 89, 147, 218
**Bug:** When Gemini/OpenAI fails, the factory silently returns TemplateProvider.
A configured `LLM_PROVIDER=gemini` failure is hidden; user gets template plans
believing they got AI plans.
**Fix (v3.0):** No silent fallback. `LLM_PROVIDER=gemini` + failure → retry →
Telegram escalation → WAITING_FOR_EXTERNAL_RESPONSE. Template only when
`LLM_PROVIDER=template` or `ALLOW_TEMPLATE_FALLBACK=true`.

### 4. 5-MINUTE HUMAN TIMEOUT (CRITICAL)
**File:** `controller/telegram_escalation.py` line 36
**Bug:** `wait_timeout = 300` — the runner polls Telegram for 5 minutes, then
gives up and uses fallback. Human intervention cannot be time-limited, and a
runner held alive wastes CI minutes.
**Fix (v3.0):** No waiting at all. Escalation message sent with RESUME_TOKEN,
state saved as WAITING_FOR_EXTERNAL_RESPONSE, runner exits. A future reply
triggers `resume.yml` workflow.

### 5. can_resume() MEANINGLESS (HIGH)
**File:** `controller/state_manager.py`
**Bug:** `return any(... for s in []) or self.get_resume_point() is not None` —
iterates over an empty list (always False), then defers entirely to
get_resume_point(). The method is misleading dead code.
**Fix (v3.0):** Real state machine with VALID transitions, `transition()`,
`can_transition()`, `mark_waiting()`, `resume_stage()`.

### 6. RENDER COLLECTOR DESTROYS WORKER IDENTITY (HIGH)
**File:** `.github/workflows/16_render_workers.yml` lines 164-165
**Bug:** `mv frame_*.png worker_0/` moves ALL frames (from every worker) into
worker_0/. Worker attribution is lost; duplicates undetectable.
**Fix (v3.0):** `RenderManager.collect_frames()` discovers worker_N/ dirs,
validates ranges, detects duplicates/missing, produces render_manifest.json
with frame→worker mapping. No file moves.

### 7. FFMPEG SILENT FALLBACK (HIGH)
**File:** `workers/ffmpeg_worker.py` line 220 (v2), `voice_tts_worker.py` `_merge_audio`
**Bug:** `except Exception: return paths[0]` — audio merge failure silently
returns only the first audio file, producing videos with truncated narration.
**Fix (v3.0):** FFmpegError raised with structured error info; retry or
escalate, never silently degrade.

### 8. Fixed-frame assumptions (MEDIUM)
**Bug:** Render partitioning assumed 20 workers / 1440 frames hard-coded in
workflow. With 4 workers available, partitions would be wrong.
**Fix (v3.0):** `RenderManager.partition_frames(total, num_workers)` — dynamic,
deterministic, no overlap/missing frames (verified by tests).

### 9. Objaverse not actually implemented (MEDIUM)
**File:** `providers/asset_provider.py`
**Bug:** Only a generic "ConfiguredAssetProvider" existed — no real Objaverse
dataset integration, despite docs implying asset API support.
**Fix (v3.0):** `providers/objaverse_provider.py` with real dataset retrieval
design, `providers/asset_router.py` with routing order
cache→objaverse→external_api→(procedural for smoke tests only).

### 10. Low-poly hard-coded (MEDIUM)
**File:** `providers/llm_provider.py`
**Bug:** System prompt hard-coded "low-poly 3D video" — anime/cinematic/realistic
styles impossible.
**Fix (v3.0):** Style-aware prompts; style flows from request to planning.

## Dangerous Assumptions (v2.0)

1. `gh workflow run` chains reliably → FALSE (artifacts don't transfer)
2. `/tmp` persists across CI runs → FALSE
3. 20 workers always available → FALSE (GitHub concurrency varies)
4. TemplateProvider fallback is always desirable → FALSE (hides failures)
5. gTTS = Google Cloud TTS → FALSE (different products, different limits)
6. `BLENDER_EEVEE` exists on all Blender versions → FALSE (4.2+ uses EEVEE_NEXT)

## Testing Gaps (v2.0)

- No tests for state transitions
- No tests for checkpoint atomicity
- No tests for error classification
- No tests for render partitioning edge cases
- No tests for Telegram reply parsing
- No tests for LLM fallback behavior
- No mock providers (tests could not run without APIs)

## Provider Limitations

- Gemini: requires GEMINI_API_KEY (PROVIDER_DEPENDENT)
- Objaverse: requires network + annotation access (PROVIDER_DEPENDENT)
- gTTS: free tier, rate limits, not Google Cloud TTS
- 3D Asset API: requires THREE_D_ASSET_API_KEY/URL (PROVIDER_DEPENDENT)

## GitHub Actions Limitations

- Artifacts don't cross workflow runs (fixed via master pipeline)
- Runner concurrency limits actual parallel workers
- Runner time limits (6h max, we use 60min for render)
- No GPU on standard runners (CPU-only rendering)
