# Objaverse

## Status: optional provider, honest unavailability
Objaverse/Objaverse-XL is an asset DATASET, not a text-to-3D API
(`providers/objaverse_provider.py`).

## Installation (optional dependency)
```bash
pip install objaverse
```
Not in `requirements.txt` on purpose — it pulls a large dependency set and is
optional. Without it, the provider returns the structured error
`PROVIDER_UNAVAILABLE` (never a silent empty list, never a fake asset). With
it, the production path performs search → candidates → ranking → metadata →
license → download → local validation → asset.

## Asset router order (unchanged)
`cache → objaverse → external 3D API → procedural fallback (test mode only)`.
Every selected asset records `ASSET_SOURCE`, asset_id, and license. License is
`UNKNOWN` when the source does not provide one — never invented.

## Testing
`TestObjaverseHonesty` (tests/test_v4.py) verifies the unavailable case;
mock-backed tests exercise the full search/rank/download/validate path
deterministically. Real network tests are NOT RUN in CI.
