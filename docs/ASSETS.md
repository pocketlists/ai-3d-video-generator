# Asset Architecture

## Provider Router (providers/asset_router.py)

Priority: CACHE → OBJAVERSE → EXTERNAL_3D_API → PROCEDURAL (test only).

PROCEDURAL is NOT an invisible production fallback. In production, if a real
asset is required and no provider can produce it, the job FAILS or ESCALATES
— it never delivers a cube as a "successful character".

## Objaverse (providers/objaverse_provider.py)

Objaverse/Objaverse-XL is an asset DATASET — NOT a text-to-3D API.

- Search: requires the `objaverse` Python package (or HF datasets API).
- If unavailable: `last_status = PROVIDER_UNAVAILABLE` and the router moves
  to the next provider — NEVER a silent empty-list "success".
- Honest statuses: `OK` / `PROVIDER_UNAVAILABLE` / `NO_RESULTS`
  (verified by `TestObjaverseHonesty`).
- Downloads only what is requested (never bulk downloads).

## External 3D API (providers/asset_provider.py)

Generic adapter over THREE_D_ASSET_API_URL + THREE_D_ASSET_API_KEY.
Capability detection (text_to_3d, image_to_3d, rigging, glb, polling) —
unsupported endpoints are never called. Handles 202 polling, timeouts,
429/401/403/5xx with error classification.

## Asset Cache (content-hash based)

`cache/assets/<content_hash>/asset.json` — keyed by provider +
provider_asset_id + prompt_hash + content_hash. Licensing metadata is
stored per asset; unknown licenses are marked `LICENSE_UNKNOWN` and are
NEVER claimed to be commercially safe.

## Asset Import (blender/asset_importer.py) — NEW in v4

GLB/GLTF/OBJ/FBX:
- Format detection (extension + magic bytes)
- Inside Blender (bpy): real import — mesh/material/texture validation,
  scale/orientation normalization, armature/animation detection,
  missing-texture detection
- Outside Blender: file-level validation (magic bytes, JSON, size) with
  `requires_blender_runtime: true` marked honestly
- Broken assets raise `AssetImportError` — never silently ignored

## Quality Tiers (PHASE 24)

background / small_prop / medium_prop / character / hero_character /
hero_closeup — separate vertex budgets per tier (config/default.yaml).
Hero characters are NOT crippled by a 500-vertex global limit.

## Character Consistency (PHASE 23)

`character_id` (e.g., hero_001) with canonical appearance/rig/materials.
All shots referencing a character reuse the same canonical asset — a new
random character is never generated per shot.
