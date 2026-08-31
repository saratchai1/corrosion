# Surat Thani 37-STC coastal-erosion / mangrove monitoring pilot

This branch applies the Samut Songkhram free-data workflow to **37-STC**, Ban Lamet, Lamet Subdistrict, Chaiya District, Surat Thani, and then extends it with a primary 10 m vegetation-edge analysis, in-plot establishment monitoring, tide sensitivity, controls, and a conservative Sentinel-1 corroboration layer.

## Grounded project inputs
- **Primary/current PDD boundary: 157.55 rai** (`SHP PDD`), about **25.21 ha**; this smaller/current boundary is used for primary analysis.
- Historical/reference record: **200.05 rai** (`ยืนยันกรม`); kept for boundary history/reference only.
- **Representative intervention date: 2023-10-18**, using planting end as the before/after cutoff.
- February-April 2023 imagery is **pre-intervention**; post-intervention seasonal comparisons begin in 2024.
- Planting records: โกงกางใบใหญ่ 100,000; โกงกางใบเล็ก 40,000; ลำพู 2,232; total **142,232 seedlings**.

## Current evidence hierarchy
1. **10 m coastal vegetation edge proxy — primary satellite screening indicator.**
2. **In-plot Sentinel-2 NDVI / green fraction — planting-establishment monitoring signal.**
3. **Bank or stable geomorphic edge — preferred where a high-resolution/UAV edge can be manually validated; not automated from the current free 10 m data.**
4. **Waterline — supporting/context only.** It failed the current scene/tide robustness test.
5. **Sentinel-1 GRD — independent relative corroboration only.** It is not used as calibrated biomass or absolute backscatter evidence.

The evidence stack is deliberately separated so a positive vegetation signal cannot be misreported as proof of erosion reduction.

## Geometry and analytical coast
- `data/aoi/surat_thani_37_stc_current_aoi.geojson` — primary 157.55-rai PDD polygon.
- `data/aoi/surat_thani_37_stc_boundaries.geojson` — current and historical/reference versions.
- `data/aoi/surat_thani_37_stc_analysis_aoi.geojson` — derived 2-km surrounding-coast analysis envelope; **not** a project boundary.

The full coastal MVP contains **58 transects**. Project-frontage screening uses transects intersecting/passing within 150 m of the current PDD. Three no-known-intervention control windows use:
- rank 1: T043-T047, ~896 m from PDD;
- rank 2: T054-T058, ~1,648 m;
- rank 3: T049-T053, ~1,248 m.

On **2026-08-31** the user confirmed that these control windows have no known mangrove planting during the intervention/post period, no new seawall/breakwater/bamboo fence or other coastal-protection structure, no dredging/embankment/channel intervention, and no other known materially different intervention. The record is `data/analysis/surat_thani/control_verification.json`.

Physical coastal-setting equivalence is still satellite-screened rather than field-verified, so these are appropriate for comparative screening but not yet a causal counterfactual.

## Satellite catalogs
The implementation currently uses **Microsoft Planetary Computer** for Sentinel-2 L2A, Landsat C2 L2, and Sentinel-1 GRD.

Latest QA-passed catalogs:
- Sentinel-2: **44 selected scenes / 44 selected dates**, 2016-01-13 to 2026-04-30.
- Landsat: **235 selected scenes / 235 selected dates**, 1987-12-09 to 2026-05-26.
- Sentinel-1: **262 selected scenes / 229 selected dates**, 2015-03-02 to 2026-08-27.

Catalog summary: `data/analysis/surat_thani/catalog_summary.json`

---

# 1. Primary satellite result: 10 m coastal vegetation edge

Outputs:
- `data/analysis/surat_thani/mangrove_edge_proxy_screening.json`
- `web/public/data/surat_thani/mangrove_edge_proxy_screening.json`
- `web/public/data/surat_thani/coastal_vegetation_edge_transects.geojson`
- `web/public/data/surat_thani/coastal_vegetation_edge_points.geojson`

Method:
- Sentinel-2 B4/B8 at **native 10 m**;
- three cloud/SCL-masked February-April scenes per year, 2017-2026;
- annual median NDVI surface;
- no MNDWI water mask and no waterline in edge detection;
- fixed inland-to-seaward coastal transects;
- edge = seaward-most persistent high-NDVI run of at least 30 m;
- primary NDVI threshold **0.32**;
- sensitivity thresholds **0.28 / 0.32 / 0.36**;
- single-scene edge range is retained as an instability diagnostic.

The term **coastal vegetation edge proxy** is intentional. Sentinel-2 10 m cannot by itself confirm that every detected high-NDVI pixel is planted mangrove.

### Primary threshold 0.32
Project frontage (23 transects):
- observation completeness: **98.3%**;
- median pre-2017→2023 edge slope: **-1.429 m/year**;
- median post-2024→2026 slope: **0.000 m/year**;
- median 2023→2026 edge change: **0.0 m**.

Pooled controls (15 transects):
- observation completeness: **92.7%**;
- median pre slope: **-2.286 m/year**;
- median post slope: **0.000 m/year**;
- median 2023→2026 edge change: **0.0 m**.

Project minus control:
- 2023→2026 net edge-change contrast: **0.0 m**;
- slope-change contrast: **-0.857 m/year**.

Across all three NDVI thresholds, the 2023→2026 project-minus-control net contrast is **0.0 m / 0.0 m / 0.0 m**. The empirical edge-instability floor is at least **10 m**, and the project single-scene edge range has median ~10 m with p90 ~95 m.

### Interpretation
**No project-relative seaward advance of the persistent coastal-vegetation edge is detectable at the 10 m Sentinel-2 scale from 2023 to 2026.**

This does **not** mean the planting failed. Young/sparse seedlings can be alive and growing while occupying too little of a 10×10 m pixel to create a stable high-NDVI edge shift.

---

# 2. Planting-establishment screening inside the 157.55-rai PDD

Outputs:
- `data/analysis/surat_thani/planting_establishment_screening.json`
- `data/analysis/surat_thani/vegetation_control_windows.geojson`
- `web/public/data/surat_thani/planting_establishment_screening.json`
- `web/public/data/surat_thani/vegetation_control_windows.geojson`

This analysis asks a different question from shoreline change: **did greenness / green-pixel occupancy inside the planted PDD increase relative to no-known-intervention controls?**

Control pseudo-project windows use the median cross-shore span of the PDD where project transects intersect it:
- median interval ~1497.1 to 1620.7 m along the fixed transects;
- median cross-shore span **123.6 m**;
- 20 PDD-crossing transects used;
- control-window areas: **6.11, 6.10, 6.31 ha**; pooled **18.46 ha**.

Project NDVI metrics:
- median NDVI 2023: **-0.1065**;
- 2024: **-0.1237**;
- 2025: **-0.1080**;
- 2026: **-0.1072**.

Project green-pixel fraction at NDVI ≥ 0.32:
- 2023: **1.43%**;
- 2024: **1.55%**;
- 2025: **2.18%**;
- 2026: **2.30%**.

Project-vs-control 2026 minus 2023:
- median-NDVI DID-like descriptive contrast: **+0.0061**;
- NDVI ≥ 0.32 green-fraction contrast: **+0.0071 = +0.71 percentage points**;
- sign is **positive at all three tested thresholds 0.28 / 0.32 / 0.36**.

### Interpretation
There is a **small positive project-relative optical vegetation signal** after 2023. However, its magnitude is within the single-scene variability observed in the project (for example median-NDVI scene ranges ~0.0956 in 2023 and ~0.1142 in 2026).

Correct wording: **small positive monitoring signal**.

Do not convert it into:
- survival percentage;
- tree count;
- species-confirmed mangrove canopy area;
- proof of erosion reduction.

---

# 3. Waterline baseline and why it was downgraded

The first MNDWI/water-land-boundary MVP used three-scene annual composites. Near the PDD:
- project median apparent 2023→2026 change: **-4.45 m**;
- pre-2017→2023 slope: **-2.10 m/year**;
- post-2024→2026: ~**0.00 m/year**.

Baseline treatment-vs-control:
- project 2023→2026: **-4.45 m**;
- pooled controls: **0.00 m**;
- project minus control: **-4.45 m**.

These are image-derived wet/dry boundaries, not surveyed shorelines.

## Ko Prap tide context
Use **Ko Prap / เกาะปราบ, station 466**, coordinates **09°15′54″N, 99°26′04″E**, about **23.96 km** from the project centroid, only as a supporting tide reference.

Key datum/source handling:
- official 2026 RTN hourly MSL: **8,760 hourly values**;
- official 2026 comparison gives Lowest Low Water **1.43 m below MSL**;
- user-supplied ThailandTideTables URL pattern is preserved for year/month lookup;
- public ThailandTideTables heights are treated as **Chart Datum**, not silently converted to MSL;
- every selected 2023-2026 Sentinel-2 MVP scene now has at least tide stage/direction context;
- 2024 has scene-level indexed RTN MSL values;
- 2025 has public extrema phase context but no directly sourced comparable MSL series.

Products:
- `data/tide/surat_thani/ko_prap_selected_scene_stage_2023_2026.csv`
- `data/tide/surat_thani/ko_prap_selected_scene_stage_2023_2026_manifest.json`
- `web/public/data/surat_thani/tide_context.json`

## Tide-stage sensitivity test
A secondary single-scene analysis selected approximately comparable rising-stage scenes:
- 2023-02-10: rising, phase 0.5354;
- 2024-02-25: rising, ~+0.825 m MSL, relative phase unresolved;
- 2025-03-16: rising, phase 0.6042;
- 2026-04-05: rising, phase 0.3776, ~-0.441 m MSL.

Result:
- project 2023→2026: **+23.43 m**;
- pooled controls: **-3.15 m**;
- project minus control: **+26.58 m**.

The baseline project-minus-control was **-4.45 m**, so the result shifted by **+31.03 m and reversed sign**.

### Interpretation
This sign reversal demonstrates that the automated wet/dry boundary is too sensitive to scene/tide/spectral selection to support a planting-impact claim on this muddy intertidal coast.

**Waterline is therefore permanently downgraded in this pilot to supporting/contextual evidence unless a future method passes a much stronger robustness test.**

---

# 4. Bank / stable geomorphic edge

A separate automated 10 m bank-edge product is **not** being created from the current free Sentinel-2 imagery. The soft muddy/intertidal frontage does not show a consistently separable bank edge at that resolution, and automating it would produce a precise-looking but unvalidated line.

Preferred sources:
- UAV orthomosaic;
- high-resolution orthophoto;
- manually reviewed repeat high-resolution imagery.

This is an explicit methodological decision, not a missing software feature.

---

# 5. Sentinel-1 corroboration

The project includes a conservative Sentinel-1 GRD relative diagnostic:
- same repeated orbit family;
- project and controls compared **within the same scene**;
- VV, VH and VH/VV relative metrics;
- absolute backscatter/biomass interpretation is prohibited because the current data path is Level-1 GRD rather than a publication-grade calibrated RTC workflow.

A first run exposed a seasonal-filter QA issue and was **not used**. The workflow was corrected so final QA requires every selected scene to fall in February-April. Use only the latest same-season QA-passed output:
- `data/analysis/surat_thani/s1_relative_corroboration.json`

Regardless of its direction, Sentinel-1 remains **corroboration only**, not a replacement for UAV/field validation.

---

# Current integrated conclusion

The evidence now separates four questions:

1. **Did the project show a 10 m-scale coastal vegetation-edge advance?** — No detectable project-relative 2023→2026 advance.
2. **Did the planted PDD show a vegetation-establishment signal relative to controls?** — Yes, a small positive optical signal, but within single-scene variability.
3. **Does the waterline prove reduced erosion?** — No. It fails the robustness test and reverses sign with scene/tide selection.
4. **Can the current evidence support a causal erosion-reduction claim?** — **No.** UAV/high-resolution edge validation and field evidence are still required.

Recommended current language:

> ข้อมูลดาวเทียมพบสัญญาณการเพิ่มขึ้นของความเขียวภายในแปลง 37-STC เล็กน้อยเมื่อเทียบกับพื้นที่อ้างอิง แต่ยังไม่พบการขยายตัวของขอบพืชในระดับความละเอียด 10 เมตร และผล waterline มีความไวต่อระดับน้ำ/การเลือกภาพสูง จึงยังไม่สามารถสรุปว่าการปลูกช่วยลดการกัดเซาะชายฝั่งได้โดยตรง จำเป็นต้องยืนยันด้วย UAV/ภาพความละเอียดสูงและข้อมูลภาคสนาม

## Next evidence ranked by value
1. **UAV / orthophoto**: validate mangrove canopy, sparse seedlings, and actual mangrove edge inside/front of the PDD.
2. **Field survival / height / canopy observations**: turn the small optical establishment signal into biological evidence.
3. **Manual bank/stable geomorphic edge** from high-resolution repeat imagery: provide an erosion endpoint less tide-sensitive than wet/dry waterline.
4. **Repeat the same Sentinel-2 February-April protocol annually**: young planting may require additional years before a 10 m canopy/edge signal becomes detectable.
5. **If SAR is needed for publication**, rerun with calibrated RTC/incidence-angle-consistent processing.

## Browser-ready report
A standalone Surat report is scaffolded at:
- `web/public/surat-thani-37-stc.html`

It reads the committed JSON evidence stack rather than hard-coding analytical results into the page.

The final machine-readable synthesis is generated as:
- `data/analysis/surat_thani/executive_summary.json`
- `web/public/data/surat_thani/executive_summary.json`
- `regions/surat_thani/EXECUTIVE_SUMMARY_TH.md`

Until the remaining UAV/field/high-resolution validation gates are passed, the correct project status is: **monitoring evidence is improving, but current evidence does not support a causal claim that planting has reduced coastal erosion.**
