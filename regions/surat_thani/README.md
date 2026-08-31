# Surat Thani 37-STC coastal-erosion pilot

This branch applies the tested Samut Songkhram free-data workflow to **37-STC**, Ban Lamet, Lamet Subdistrict, Chaiya District, Surat Thani.

## Grounded project inputs
- **Primary/current PDD boundary: 157.55 rai** (`SHP PDD`); EPSG:32647 cross-check = **157.56 rai**. This is the smaller boundary and is used for primary analysis.
- Historical/reference record: **200.05 rai** (`ยืนยันกรม`); supplied polygon computes to about **196.21 rai**. It is kept for boundary history/reference only.
- **Representative intervention date: 2023-10-18**, using planting end as the before/after cutoff.
- February-April 2023 imagery is therefore **pre-intervention**; post-intervention seasonal comparisons begin in 2024.
- Species/counts: โกงกางใบใหญ่ 100,000; โกงกางใบเล็ก 40,000; ลำพู 2,232; total **142,232 seedlings**.

## Geometry
- `data/aoi/surat_thani_37_stc_current_aoi.geojson` — primary 157.55-rai project polygon.
- `data/aoi/surat_thani_37_stc_boundaries.geojson` — current and historical/reference versions.
- `data/aoi/surat_thani_37_stc_analysis_aoi.geojson` — derived 2-km surrounding-coast analysis envelope; **not** a project boundary.

## Satellite catalogs
The catalog workflow runs the common tested downloader against the Surat analytical AOI. The implementation currently uses **Microsoft Planetary Computer** for Sentinel-2 L2A, Landsat C2 L2, and Sentinel-1 GRD.

Latest QA-passed catalogs:
- Sentinel-2: **44 selected scenes / 44 selected dates**, 2016-01-13 to 2026-04-30.
- Landsat: **235 selected scenes / 235 selected dates**, 1987-12-09 to 2026-05-26.
- Sentinel-1: **262 selected scenes / 229 selected dates**, 2015-03-02 to 2026-08-27.

Summary: `data/analysis/surat_thani/catalog_summary.json`

Run:
```bash
python scripts/download_satellite_data_surat_thani.py sentinel2 --dry-run
python scripts/download_satellite_data_surat_thani.py landsat --dry-run
python scripts/download_satellite_data_surat_thani.py sentinel1 --dry-run
```

## Coastal-change MVP
The bounded optical MVP has been built and QA-passed with:
- **14 epochs**: long-term Landsat context plus annual/seasonal Sentinel-2 through 2026.
- **58 transects** over the surrounding Chaiya coast.
- automated MNDWI-derived water-land boundary proxies;
- NDVI coastal-vegetation proxies;
- browser-ready imagery, boundaries, transects and statistics under `web/public/data/surat_thani/`.

The full-coast output is intentionally broader than the project plot. To avoid presenting surrounding coastline as if it were 37-STC, a separate frontage screen selects transects that intersect or pass within 150 m of the current 157.55-rai PDD polygon.

### 37-STC frontage screen
`web/public/data/surat_thani/project_frontage_summary.json`

Current first-pass results:
- **23 / 58 transects** selected near the current PDD polygon.
- median image-derived boundary position fell from **+3.16 m (2023)** to **-2.68 m (2026)** relative to the 2026 reference geometry.
- median apparent 2023→2026 change across selected transects: **-4.45 m** (positive direction = seaward).
- median per-transect pre-intervention slope, 2017-2023: **-2.10 m/year**.
- median per-transect post-period slope, 2024-2026: approximately **0.00 m/year**.
- selected-transect long-term classes from the MVP: 12 apparent erosion, 9 stable, 2 apparent accretion.

The apparent slowing after 2023 is a **screening signal only**. Annual median positions are not monotonic (2024 -1.15 m, 2025 +3.84 m, 2026 -2.68 m), so tide state, image conditions, indicator choice and field validation remain important.

## Control/reference comparison
The satellite pretrend screen selected three spatially separated reference windows outside the current PDD neighbourhood:
- rank 1: T043-T047, median distance about 896 m from the PDD;
- rank 2: T054-T058, median distance about 1,648 m;
- rank 3: T049-T053, median distance about 1,248 m.

On **2026-08-31**, the project user confirmed for these selected control windows that there was **no mangrove planting during the intervention/post period, no new seawall/breakwater/bamboo fence or other coastal-protection structure, no dredging/embankment/channel intervention, and no other known materially different intervention**. This confirmation is recorded in `data/analysis/surat_thani/control_verification.json`.

The treatment-control comparative screening is in `data/analysis/surat_thani/comparative_screening.json` and `web/public/data/surat_thani/comparative_screening.json`.

Key descriptive results:
- 37-STC frontage median pre slope: **-2.102 m/year**; post slope: **~0.000 m/year**; post-minus-pre change: **+2.102 m/year**.
- pooled 15 control transects median pre slope: **-1.263 m/year**; post slope: **+1.625 m/year**; post-minus-pre change: **+2.888 m/year**.
- project-minus-control slope-change contrast: **-0.786 m/year**.
- 2023→2026 apparent boundary change: project **-4.45 m**, pooled controls **0.00 m**; project-minus-control contrast **-4.45 m**.

Therefore the apparent post-2023 slowing is **not stronger at the project frontage than in the selected no-known-intervention controls**. In this first-pass automated water-land-boundary analysis, the controls improved at least as much as, and by the slope-change metric more than, the project frontage. This weakens any interpretation that the observed slowing is uniquely attributable to planting and points to broader coastal variability, tide/image effects, or other shared drivers as plausible explanations.

This remains a descriptive screening comparison, not a formal causal difference-in-differences estimate. Physical coastal-setting equivalence still requires review and field/UAV validation remains an evidence gate.

## Ko Prap tide reference
Use **Ko Prap / เกาะปราบ, station 466**, coordinates **09°15′54″N, 99°26′04″E** (WGS84), about **23.96 km** from the current project-boundary centroid, as a supporting tide-screening reference. It is not an in-plot water-level gauge.

Two official 2026 Royal Thai Navy Hydrographic Department tables establish the datum treatment:
- `KP2026.pdf` — hourly predictions above **Lowest Low Water / chart datum**.
- `KP2026msl.pdf` — hourly predictions above **Mean Sea Level (MSL)**.
- official comparison table gives Ko Prap Lowest Low Water as **1.43 m below MSL**.

The live reproducible 2026 MSL source is:
`https://hydro.navy.mi.th/storage/frontend/article/23019/file/th/KP2026msl.pdf`

The pipeline parses **8,760 hourly 2026 MSL values** and matches scene time by exact hour or linear interpolation with a maximum 90-minute bracketing gap.

For the three selected 2026 Sentinel-2 scenes, matched predicted Ko Prap levels are approximately:
- 2026-03-01 10:37 ICT: **+1.038 m MSL**
- 2026-04-05 10:35 ICT: **-0.441 m MSL**
- 2026-04-30 10:35 ICT: **-0.100 m MSL**

For 2023, the official historical product currently available to the project is an extrema table above **Lowest Low Water**, not a reproducibly downloadable hourly MSL archive. The three selected February-April 2023 scenes have therefore been preserved only as official extrema **stage/phase context**; all three occur on a rising tide. Numeric LLW heights are not mixed with the 2026 MSL series.

The user-supplied public URL pattern is retained as a manual fallback:
`https://www.thailandtidetables.com/ไทย/ตารางน้ำขึ้นน้ำลง-เกาะปราบ-สุราษฎร์ธานี-ปี-{year}-{month:02d}-466.php`

That site returned HTTP 403 from GitHub Actions, so CI does not depend on it.

Tide products:
- `data/tide/surat_thani/ko_prap_hourly_msl.csv`
- `data/tide/surat_thani/ko_prap_hourly_msl_manifest.json`
- `data/catalog/surat_thani_mvp_optical_scenes_tide_msl.csv`
- `data/tide/surat_thani/ko_prap_2023_selected_scene_phase.csv`
- `web/public/data/surat_thani/tide_context.json`

Current waterline tide gate is **PARTIAL_TIDE_CONTEXT_ONLY** because reproducible hourly MSL for 2024-2025 is not yet committed. Do not describe the whole 2023-2026 waterline sequence as fully tide-normalized.

## Interpretation hierarchy
1. Prefer **mangrove edge** as the primary image indicator.
2. Use **bank edge** as primary where clearly visible.
3. Use **waterline** only as supporting evidence with tide metadata.
4. Keep automated spectral boundaries labelled **image-derived**, never surveyed shoreline.
5. The selected controls have user-confirmed absence of known intervention, but do not make a planting-impact claim until physical-setting review, uncertainty checks and UAV/field validation are complete.

## What remains before an impact claim
- obtain reproducible tide context for 2024-2025 or constrain image comparison to comparable tide stage;
- manually/orthophoto validate mangrove edge or bank edge;
- verify physical coastal-setting comparability of the three selected control windows;
- add UAV or field validation at 37-STC and preferably controls;
- estimate positional uncertainty and test sensitivity to scene/tide selection.

Until those gates are passed, the correct claim is: **satellite screening shows a change in image-derived coastal-boundary behaviour near 37-STC, but the selected no-known-intervention controls show equal or stronger post-2023 improvement, so current evidence does not support attributing the apparent slowing to planting.**
