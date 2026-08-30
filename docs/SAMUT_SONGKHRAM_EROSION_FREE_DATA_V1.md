# Samut Songkhram erosion analysis — free-data implementation v1

## Objective

Use only:

- free Landsat, Sentinel-2 and supporting Sentinel-1 data;
- free predicted tide tables or a documented open tide model;
- routine UAV surveys inside project plots; and
- simple field observations collected during normal site visits.

The target claim is intentionally narrow:

> Determine whether the seaward mangrove edge or bank edge in front of the planting plots retreats less after planting than before planting and than comparable unplanted coastal segments.

No sediment sampling, wave gauge or current meter is required for this evidence tier. Consequently, this work will not quantify sediment trapping, wave reduction or storm-damage avoidance.

## Existing evidence reused

The existing project already provides:

- nine plot geometries: `91–98-STC` and `87-VSD`;
- January–April Sentinel-2 project composites for 2023–2026;
- province context from Landsat and Sentinel-2;
- image-derived water-land boundaries and transects;
- 43 current plot-crossing transects for `91–98-STC`; and
- a conservative conclusion of `NOT_DEMONSTRATED` with `LOW` confidence.

The present blocker is not a lack of satellite imagery. It is that the existing edge is an image-derived water-land boundary, the exact planting date is ambiguous, controls are not designed as coastal controls, UAV/field boundaries are not yet standardized, and `87-VSD` has no comparable transect coverage.

## Verified tide baseline as of 2026-08-30

The official Pak Nam Mae Klong 2026 MSL PDF was parsed and validated successfully:

- 8,760 hourly predictions;
- all 365 days and 24 values per day recovered;
- source PDF checksum and page-level parsing metadata retained;
- all three 2026 Sentinel-2 project scenes matched by interpolation; and
- nine scenes from 2023–2025 left explicitly unmatched.

The former official annual PDF URLs for 2023–2025 returned HTTP 404. Missing values were not copied from another year, inferred from a search-result snippet or silently replaced. The resulting tide-matched fraction is 25%, so the evidence level correctly remains `SATELLITE_SCREENING` rather than `TIDE_AWARE_SCREENING`.

Versioned outputs:

```text
data/tide/samut_songkhram/pak_nam_mae_klong_hourly_msl.csv
data/tide/samut_songkhram/pak_nam_mae_klong_hourly_msl_manifest.json
data/tide/samut_songkhram/pak_nam_mae_klong_source_availability.json
data/catalog/project_samut_songkhram_sentinel2_scenes_tide_matched.csv
data/processed/project_impact/erosion_readiness.json
```

## Work package 1 — complete tide-aware scene coverage

1. retain the verified 2026 official MSL baseline;
2. recover cited official 2023–2025 annual tables where possible, or select one consistent open tide model for all four years;
3. document station/model, datum or reference convention, coordinates, temporal resolution, version and licence;
4. validate any open-model series against the official 2026 station predictions before use;
5. match scene acquisition times using `scripts/match_scene_tides.py`;
6. retain unmatched scenes explicitly; and
7. use tide primarily to screen waterline observations, not to manufacture a surveyed shoreline.

Do not lower the configured 80% tide-matched threshold merely to promote the evidence level.

## Work package 2 — correct boundary indicators

Track separate indicators:

| Indicator | Role | Main source |
|---|---|---|
| `MANGROVE_EDGE` | Primary | Sentinel-2 seasonal composite + UAV |
| `BANK_EDGE` | Primary where visible | UAV + fixed field observations |
| `WATERLINE` | Supporting only | Landsat/Sentinel-2 with tide metadata |

Never merge these three indicators into one time series without retaining the indicator type.

## Work package 3 — project and control transects

- Create 50 m transects along each project frontage.
- Extend coverage to `87-VSD`.
- Retain adjacent left/right coast segments.
- Select at least three candidate control segments for each treatment setting.
- Reject controls with different pre-2024 trends or different structures, dredging, reclamation or planting history.
- Calculate NSM, EPR, LRR and SCE separately by boundary indicator.

The causal comparison is:

```text
(after - before) project frontage - (after - before) control frontage
```

## Work package 4 — routine UAV and field evidence

UAV surveys should include the seaward edge, bank edge, a narrow fronting mudflat strip, channel connections and plot corners. Repeat the same season, tide window, flight plan, altitude and overlap where practical. Record RTK/GCP use and horizontal RMSE.

During normal site visits, collect fixed-point photos, GPS, time, boundary type, distance from a fixed marker where possible, root exposure, fallen trees and new channels. No sediment sample is required.

Templates:

- `data/templates/samut_songkhram_drone_survey_metadata.csv`
- `data/templates/samut_songkhram_field_boundary_observations.csv`

## Evidence gates

Run:

```bash
python scripts/audit_samut_songkhram_erosion_readiness.py
```

The audit reports one of:

1. `INSUFFICIENT_DATA`
2. `SATELLITE_SCREENING`
3. `TIDE_AWARE_SCREENING`
4. `OBSERVED_STABILIZATION`
5. `COMPARATIVE_EFFECT`

The program may only use the claim sentence mapped to the current evidence level in `config/samut_songkhram_erosion_free_data_v1.json`.

## Immediate next input required from operations

The analysis team can proceed without new paid instruments, but operations should supply:

- exact or best-known planting dates for each plot;
- any replanting dates;
- presence of bamboo fences, seawalls, breakwaters or other structures;
- existing UAV orthomosaics and flight metadata; and
- any fixed-point field photographs already collected.

## Current status

```text
SATELLITE_SCREENING
```

Current allowed wording:

> ผลดาวเทียมเป็นการคัดกรองเบื้องต้นและยังไม่ยืนยันผลของการปลูกต่อการกัดเซาะชายฝั่ง

Current major blockers:

- only 3 of 12 project scenes have verified tide metadata;
- exact planting dates are not verified;
- `87-VSD` lacks boundary-transect coverage;
- no standardized repeat UAV or field-boundary records are versioned;
- coastal control segments are not verified; and
- only two post-treatment years are configured.
