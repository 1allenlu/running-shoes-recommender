# Hand-written foot profiles

Made-up `FootProfile`s (not real scans) covering cases the ranker must handle, for the
Phase 3 CLI check alongside `data/sample_scans/expected_profile.json`:

| File | Case |
| --- | --- |
| `01_narrow_high_instep.json` | B width, high instep, narrow heel |
| `02_standard_neutral.json` | D width, everything mid-scale |
| `03_wide_high_instep.json` | 2E width, high instep, wide heel (needs a wide version) |
| `04_womens_wide_low_instep_narrow_heel.json` | women's scale D (wide), low instep, narrow heel |
| `05_mismatched_feet.json` | right foot longer and wider than the left |

```
uv run python -m app.ranking.pipeline --profile data/profiles/03_wide_high_instep.json \
    --prefs data/profiles/example_preferences.json --history data/profiles/example_history.json
```
