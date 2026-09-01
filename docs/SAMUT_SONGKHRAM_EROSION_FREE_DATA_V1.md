# Samut Songkhram erosion analysis — free-data implementation v1

## Objective

Use only:

- free Landsat, Sentinel-2 and supporting Sentinel-1 data;
- free predicted tide tables or a documented open tide source;
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
- a conservative conclusion of `NOT_DEMONSTRATED` with `LOW` confidence for erosion effect.

The present blocker is no longer a lack of tide metadata. It is that the existing boundary is still an image-derived water-land boundary, the exact planting date is ambiguous, controls are not verified as coastal controls, UAV/field boundaries are not yet standardized, and `87-VSD` has no comparable transect coverage.

## Tide-aware scene coverage as of 2026-08-30

### Official 2026 hourly baseline

The official Pak Nam Mae Klong 2026 MSL PDF was parsed and validated successfully:

- 8,760 hourly predictions;
- all 365 days and 24 values per day recovered;
- source PDF checksum and page-level parsing metadata retained; and
- all three 2026 Sentinel-2 project scenes matched by interpolation.

### Secondary 2023–2025 extrema

The former official annual PDF URLs for 2023–2025 returned HTTP 404. All 36 monthly ThailandTideTables pages were therefore collected as a separately identified secondary source, producing 3,608 published high/low extrema:

- 2023: 1,208;
- 2024: 1,199; and
- 2025: 1,201.

The source site reports Chart Datum and attributes its data to World Tides and the Hydrographic Department, Royal Thai Navy. Values were converted to candidate MSL using the published Pak Nam Mae Klong offset:

```text
MSL candidate = published Chart Datum height - 2.14 m
```

The conversion was validated against the official 2026 hourly MSL series using the 2026 secondary extrema:

- MAE: 0.02215 m;
- RMSE: 0.02723 m;
- bias: -0.00040 m;
- 95th-percentile absolute error: 0.05000 m; and
- maximum absolute error: 0.07000 m.

The nine previously unmatched 2023–2025 Sentinel-2 scenes were then assigned screening estimates using cosine interpolation between consecutive published extrema. The maximum interpolation bracket used by a project scene is 17.71667 hours. The three official 2026 matches remain unchanged.

The project scene catalog now has tide metadata for 12 of 12 scenes, so the evidence gate is:

```text
TIDE_AWARE_SCREENING
```

This does not demonstrate an erosion effect. It means scene comparison now includes traceable tide context, with official and secondary source tiers kept separate.

Versioned outputs:

```text
data/tide/samut_songkhram/pak_nam_mae_klong_hourly_msl.csv
data/tide/samut_songkhram/pak_nam_mae_klong_hourly_msl_manifest.json
data/tide/samut_songkhram/pak_nam_mae_klong_2023_2025_secondary_extrema.csv
data/tide/samut_songkhram/pak_nam_mae_klong_2023_2025_secondary_extrema_manifest.json
data/tide/samut_songkhram/pak_nam_mae_klong_secondary_extrema_2026_validation.json
data/catalog/project_samut_songkhram_sentinel2_scenes_tide_matched.csv
data/processed/project_impact/erosion_readiness.json
```

## Work package 1 — maintain tide-aware scene coverage

1. retain the verified official 2026 hourly MSL baseline;
2. retain the secondary 2023–2025 extrema as a distinct source tier;
3. preserve source URL, retrieval URL, datum conversion, validation metrics and interpolation brackets;
4. replace a secondary year with an official annual table if a cited copy is recovered;
5. never relabel secondary interpolation as an observed or official hourly value; and
6. use tide primarily to screen waterline observations, not to manufacture a surveyed shoreline.

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
TIDE_AWARE_SCREENING
```

Current allowed wording:

> ผลดาวเทียมที่คัดตามระดับน้ำสนับสนุนการติดตามแนวโน้ม แต่ยังต้องตรวจด้วยโดรนหรือภาคสนาม

Current major blockers:

- exact planting dates are not verified;
- `87-VSD` lacks boundary-transect coverage;
- no standardized repeat UAV or field-boundary records are versioned;
- coastal control segments are not verified; and
- only two post-treatment years are configured.
