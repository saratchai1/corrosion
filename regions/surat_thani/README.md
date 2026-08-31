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

### 37-STC frontage screen — baseline three-scene composites
`web/public/data/surat_thani/project_frontage_summary.json`

Baseline first-pass results:
- **23 / 58 transects** selected near the current PDD polygon.
- median image-derived boundary position fell from **+3.16 m (2023)** to **-2.68 m (2026)** relative to the 2026 reference geometry.
- median apparent 2023→2026 change across selected transects: **-4.45 m** (positive direction = seaward).
- median per-transect pre-intervention slope, 2017-2023: **-2.10 m/year**.
- median per-transect post-period slope, 2024-2026: approximately **0.00 m/year**.
- selected-transect long-term classes from the MVP: 12 apparent erosion, 9 stable, 2 apparent accretion.

The apparent slowing after 2023 was a screening signal only. Annual median positions were not monotonic (2024 -1.15 m, 2025 +3.84 m, 2026 -2.68 m), motivating the tide-stage sensitivity test below.

## Control/reference comparison
The satellite pretrend screen selected three spatially separated reference windows outside the current PDD neighbourhood:
- rank 1: T043-T047, median distance about 896 m from the PDD;
- rank 2: T054-T058, median distance about 1,648 m;
- rank 3: T049-T053, median distance about 1,248 m.

On **2026-08-31**, the project user confirmed for these selected control windows that there was **no mangrove planting during the intervention/post period, no new seawall/breakwater/bamboo fence or other coastal-protection structure, no dredging/embankment/channel intervention, and no other known materially different intervention**. This confirmation is recorded in `data/analysis/surat_thani/control_verification.json`.

The baseline treatment-control comparative screening is in `data/analysis/surat_thani/comparative_screening.json` and `web/public/data/surat_thani/comparative_screening.json`.

Baseline descriptive results:
- 37-STC frontage median pre slope: **-2.102 m/year**; post slope: **~0.000 m/year**; post-minus-pre change: **+2.102 m/year**.
- pooled 15 control transects median pre slope: **-1.263 m/year**; post slope: **+1.625 m/year**; post-minus-pre change: **+2.888 m/year**.
- project-minus-control slope-change contrast: **-0.786 m/year**.
- 2023→2026 apparent boundary change: project **-4.45 m**, pooled controls **0.00 m**; project-minus-control contrast **-4.45 m**.

In the baseline three-scene composite, the apparent post-2023 slowing was therefore **not stronger at the project frontage than in the selected no-known-intervention controls**.

## Ko Prap tide reference and 2024-2025 URL recovery
Use **Ko Prap / เกาะปราบ, station 466**, coordinates **09°15′54″N, 99°26′04″E** (WGS84), about **23.96 km** from the current project-boundary centroid, as a supporting tide-screening reference. It is not an in-plot water-level gauge.

Two official 2026 Royal Thai Navy Hydrographic Department tables establish the datum treatment:
- `KP2026.pdf` — hourly predictions above **Lowest Low Water / chart datum**.
- `KP2026msl.pdf` — hourly predictions above **Mean Sea Level (MSL)**.
- official comparison table gives Ko Prap Lowest Low Water as **1.43 m below MSL**.

The live reproducible 2026 MSL source is:
`https://hydro.navy.mi.th/storage/frontend/article/23019/file/th/KP2026msl.pdf`

The user-supplied ThailandTideTables URL pattern was expanded by changing year/month directly:
`https://www.thailandtidetables.com/ไทย/ตารางน้ำขึ้นน้ำลง-เกาะปราบ-สุราษฎร์ธานี-ปี-{year}-{month:02d}-466.php`

The public pages label their heights as **Chart Datum** and cite World Tides / Royal Thai Navy Hydrographic Department. The website has returned HTTP 403 from GitHub Actions, so CI does not scrape it. Instead, the sourced scene-level values and URLs are committed in:
- `data/tide/surat_thani/ko_prap_selected_scene_stage_2023_2026.csv`
- `data/tide/surat_thani/ko_prap_selected_scene_stage_2023_2026_manifest.json`

Scene-level context now covers all selected 2023-2026 Sentinel-2 MVP scenes:
- **2023:** all three scenes are rising; relative phases 0.5354, 0.3558, 0.7138 from preserved RTN extrema context.
- **2024:** official indexed RTN MSL content gives approximately **+0.825 m MSL** on 25 Feb (rising), **+0.641 m MSL** on 21 Mar (near high/early falling), and **+0.300 m MSL** on 20 Apr (falling). The historical 2024 PDF URL is no longer live, so provenance is explicitly marked indexed/non-live.
- **2025:** ThailandTideTables extrema give 14 Feb rising phase **0.8502**, 16 Mar rising phase **0.6042**, and 7 Apr falling phase **0.4189**. Heights remain Chart Datum and are **not** silently converted to MSL.
- **2026:** the official hourly RTN MSL catalog contains 8,760 values. The three selected scenes match approximately **+1.038**, **-0.441**, and **-0.100 m MSL**; public extrema also provide stage/phase context.

The web tide gate is now **SCENE_LEVEL_TIDE_CONTEXT_2023_2026_PARTIAL_MSL**: every selected 2023-2026 scene has at least stage/direction context, while 2025 still lacks a directly sourced comparable MSL series. This is better than the previous missing-2024/2025 state but is still not a fully MSL-normalized shoreline series.

## Tide-stage constrained sensitivity test
To test whether mixed tide states were driving the baseline waterline result, a **secondary single-scene sensitivity run** was added without overwriting the baseline. The selection target is the pre-intervention 2023 rising-tide median phase (**0.5354**).

Selected scenes:
- 2023-02-10 — rising, phase **0.5354**;
- 2024-02-25 — rising, official RTN scene level about **+0.825 m MSL**; relative extrema phase unresolved;
- 2025-03-16 — rising, phase **0.6042**;
- 2026-04-05 — rising, phase **0.3776**, official scene level about **-0.441 m MSL**.

Selection and outputs:
- `data/analysis/surat_thani/tide_matched_scene_selection.json`
- `data/processed/surat_thani_tide_matched/`
- `web/public/data/surat_thani/tide_matched/`
- `data/analysis/surat_thani/tide_matched_sensitivity_summary.json`
- `web/public/data/surat_thani/tide_matched_sensitivity_summary.json`

### Sensitivity result — waterline is not robust
The single-scene tide-stage-constrained run gives:
- project frontage: **+23.43 m** apparent 2023→2026 movement;
- pooled controls: **-3.15 m**;
- project-minus-control contrast: **+26.58 m**;
- post-2024→2026 median slope: project **+16.18 m/year**, pooled controls **+5.315 m/year**.

This is the **opposite sign** of the baseline three-scene result, where project-minus-control 2023→2026 was **-4.45 m**. The sensitivity shift in that contrast is **+31.03 m**.

This sign reversal is more important than either individual number. It demonstrates that the automated spectral wet/dry boundary is **highly sensitive to scene/tide/spectral selection** at this muddy intertidal coast. Therefore the waterline indicator fails the robustness test for an impact claim. Neither the baseline negative contrast nor the tide-stage positive contrast should be presented as evidence that planting increased or reduced erosion.

The correct use of waterline from this pipeline is now **supporting/contextual screening only**. The next primary analytical effort should move to **mangrove edge** and **bank edge where visible**, followed by UAV/field validation.

## Interpretation hierarchy
1. Prefer **mangrove edge** as the primary image indicator.
2. Use **bank edge** as primary where clearly visible.
3. Use **waterline** only as supporting/contextual evidence; it has failed the current scene-selection robustness test.
4. Keep automated spectral boundaries labelled **image-derived**, never surveyed shoreline.
5. The selected controls have user-confirmed absence of known intervention, but do not make a planting-impact claim until physical-setting review, uncertainty checks and UAV/field validation are complete.

## What remains before an impact claim
- manually/orthophoto extract and validate **mangrove edge** or **bank edge** using repeated comparable imagery;
- verify physical coastal-setting comparability of the three selected control windows;
- add UAV or field validation at 37-STC and preferably controls;
- estimate positional uncertainty for mangrove/bank edge and test threshold/manual-digitizing sensitivity;
- use tide-matched waterline only as a secondary consistency check, not the main endpoint.

Until those gates are passed, the correct claim is: **the automated waterline result is not robust to scene/tide selection and cannot support a planting-impact conclusion. The project should be evaluated primarily with mangrove-edge/bank-edge change plus control and field/UAV evidence.**
