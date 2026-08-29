# Samut Songkhram 2024 planting assessment

## Direct answer

The current satellite evidence does **not demonstrate that the reported 2024 mangrove planting reduced coastal erosion**. The result is `LOW` confidence rather than evidence of no effect: the project plots became greener, and most available plot-crossing water–land positions were stable in the latest year, but neither signal is uniquely attributable to planting.

## Verified scope

Only the nine Samut Songkhram records identified in the pinned `saratchai1/mangrove-drone-dashboard` source are used:

`91-STC`, `92-STC`, `93-STC`, `94-STC`, `95-STC`, `96-STC`, `97-STC`, `98-STC`, and `87-VSD`.

Official participating area from `areaTable.csv` totals **628.585 rai**. Unioned polygon geometry calculates to **638.703 rai**. The difference is retained as geometry QA, not used to replace the official total. `87-VSD` has the largest discrepancy: geometry is 9.36% above its table area. Coordinates come from `web/src/data/plotBoundaries.ts` at commit `825d91b8d6d9f3c0e224e71266d7d2ced7cf4dc9`; that file states it was generated from `kmz/STC_VSD_EVR.kmz`.

## Satellite design

- Sentinel-2 Level-2A surface reflectance, 20 m analysis grid.
- Three low-bad-quality acquisitions per year.
- Same seasonal window: January–April 2023, 2024, 2025, and 2026.
- 2023 is the pre-project reference; 2024 is marked `intervention_ambiguous` because the exact planting date is not verified; 2025 and 2026 are post years.
- Cloud, shadow, cirrus, invalid, and snow classes are removed with Sentinel-2 SCL before median compositing.
- Tide remains `unverified`.

The analytical imagery AOI is the union of 2.5 km buffers around the nine plots. This buffer supports nearby context selection and is not an official project boundary.

## Vegetation and wetness evidence

Across all nine plot geometries:

| Year | Role | Mean NDVI | NDVI ≥ 0.35 | Mean MNDWI | MNDWI > 0 |
|---:|---|---:|---:|---:|---:|
| 2023 | pre | 0.40349 | 91.13% | -0.12096 | 0.79% |
| 2024 | intervention ambiguous | 0.44898 | 95.29% | -0.16044 | 0.28% |
| 2025 | post | 0.46378 | 95.76% | -0.14917 | 0.63% |
| 2026 | post | 0.47230 | 97.25% | -0.15309 | 0.43% |

Mean NDVI increased by **0.0688** between 2023 and 2026, and all nine plots have a positive plot-level mean NDVI change. This is consistent with increased green vegetation signal, but not necessarily new mangrove canopy: existing vegetation growth, seasonal moisture, mixed pixels, and other vegetation can contribute.

The nearby comparison area is 200–1,200 m from the project polygons and filtered to the central 90% of the plots' 2023 NDVI and MNDWI ranges. It is observational context, not a randomized or field-verified control. Difference-in-differences results are:

| Post year | NDVI DiD | Vegetation-fraction DiD | Water-fraction DiD |
|---:|---:|---:|---:|
| 2025 | -0.00498 | -0.05918 | -0.00259 |
| 2026 | +0.00534 | -0.04307 | -0.00506 |

The near-zero 2026 NDVI DiD means the local comparison pixels greened by almost the same amount as the plots. Therefore, the positive plot NDVI trend cannot currently be isolated as a planting effect.

## Water–land boundary evidence

The existing province-wide transects intersect 43 locations across `91–98-STC` in 2025–2026:

- 34 are within ±20 m;
- 5 move inland by more than 20 m;
- 4 move seaward by more than 20 m;
- median apparent movement is **-0.68 m**;
- mean apparent movement is **-4.11 m**.

This is compatible with mostly stable recent image-derived water–land positions, but it is only a one-year post-period and is not tide-normalized. `87-VSD` falls outside the existing province-wide transect AOI, so it currently has plot spectral metrics but no comparable boundary-transect result.

## Why causality is not established

1. The exact 2024 planting date, planting rows, species, density, and survival are not verified.
2. There is only one clean pre year and two early post years; young seedlings may be smaller than a 20 m pixel.
3. Tide, waves, mudflat moisture, sediment supply, and elevation change are unavailable.
4. The matched context is selected from satellite baselines, not a field-designed control coast.
5. The mapped line is an **image-derived water–land boundary**, not a surveyed or tide-normalized shoreline.
6. NDVI is a vegetation proxy, not a validated mangrove classifier.

## Outputs

- Plot geometry and area QA: `data/aoi/samut_songkhram_project_plots.geojson`
- Buffered analysis AOI: `data/aoi/samut_songkhram_project_analysis_aoi.geojson`
- Scene catalog: `data/catalog/project_samut_songkhram_sentinel2_scenes.csv`
- Plot/year metrics: `data/processed/project_impact/plot_yearly_metrics.csv`
- Matched-context metrics: `data/processed/project_impact/matched_control_comparison.csv`
- Plot change summary: `data/processed/project_impact/plot_change_summary.csv`
- Boundary evidence: `data/processed/project_impact/post_boundary_transects.csv`
- Machine-readable conclusion: `data/processed/project_impact/summary.json`

Source and composite TIFFs are stored on the local hard disk and ignored by Git. Catalogs, checksums, small vectors/tables, summaries, and optimized WebP previews are versioned.
