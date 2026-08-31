---
name: thailand-mangrove-coastal-erosion-province
description: Reusable workflow for building a free-data, tide-aware mangrove coastal-erosion evidence pipeline and production web dashboard for any Thai province, based on the Samut Songkhram implementation.
---

# Thailand Mangrove Coastal-Erosion Province Skill

## Purpose

ใช้ skill นี้เมื่อผู้ใช้สั่งให้ทำจังหวัดใหม่ในลักษณะเดียวกับงานสมุทรสงคราม เช่น ระยอง กระบี่ พังงา ภูเก็ต ระนอง สตูล หรือจังหวัดชายฝั่งอื่น ๆ โดยเป้าหมายคือสร้างหลักฐานจาก **ข้อมูลฟรีบนอินเทอร์เน็ต + ข้อมูลโครงการที่มีอยู่แล้ว + โดรน/ภาคสนามที่ต้องทำตามปกติ** เพื่อประเมินว่าแนวชายฝั่งก่อนและหลังการปลูกป่าชายเลนเปลี่ยนอย่างไร และหลักฐานไปได้ไกลแค่ไหนในการสนับสนุนคำกล่าวเรื่องการลดการกัดเซาะ

งานต้องจบเป็น pipeline ที่ทำซ้ำได้, มี QA/claim guard, มีผลลัพธ์ machine-readable และมีเว็บ production ที่คนทั่วไปอ่านเข้าใจได้

## Golden rule

**อย่าเริ่มใหม่จากศูนย์**

ให้ใช้โครงสร้างและ pattern จาก Samut Songkhram ใน repo `saratchai1/corrosion` เป็น template แล้ว parameterize จังหวัดใหม่ เช่น province key, AOI, plot IDs, tide station, datum, planting dates, time range, output path และ production project name

ห้าม copy ตัวเลขเฉพาะสมุทรสงครามไปใช้กับจังหวัดอื่นโดยไม่ตรวจใหม่ โดยเฉพาะ:

- tide station
- datum offset ระหว่าง Chart Datum / LLW / MSL
- target tide
- accepted tide tolerance
- UTM zone / analysis CRS
- plot IDs
- planting dates
- control areas
- scene dates
- shoreline orientation

## Required user inputs

ถ้ามี ให้ขอ/ใช้ข้อมูลเหล่านี้ก่อน แต่ **อย่าหยุดงานเพียงเพราะยังไม่ครบ** ให้ทำจากข้อมูลฟรีที่หาได้ก่อนและระบุช่องว่างไว้

1. ขอบแปลงจริง: KMZ/KML/GeoJSON/Shapefile
2. รหัสแปลงและจังหวัด
3. วันเริ่มปลูก / วันปลูกเสร็จ / วันปลูกซ่อม อย่างน้อยเดือน-ปี
4. พื้นที่ปลูกจริง (rai) และพื้นที่ตาม PDD ถ้ามี
5. รูป/orthomosaic/flight log จากโดรน ถ้ามี
6. ข้อมูลโครงสร้างชายฝั่ง: ไม้ไผ่ เขื่อนหิน geotube seawall ฯลฯ
7. พื้นที่ใกล้เคียงที่รู้ว่าไม่ได้ปลูก ถ้ามี

ถ้าผู้ใช้ส่ง screenshot ตารางวันปลูก ให้เก็บเป็น evidence record แยกจากข้อมูลที่อนุมาน ห้ามเดาวันเริ่มปลูกจากวันปลูกเสร็จ

## Free-data sources

### Satellite

ใช้ลำดับหลัก:

- Sentinel-2 L2A — Earth Search `sentinel-2-l2a`
- Landsat Collection 2 L2 — Microsoft Planetary Computer `landsat-c2-l2`
- Sentinel-1 GRD — Microsoft Planetary Computer `sentinel-1-grd`

Sentinel-2 เป็นแกนหลักสำหรับ RGB, False Color, NDVI, MNDWI, SWIR composite และ image-derived waterline / vegetation edge

Landsat ใช้เพิ่ม historical depth ถ้าต้องย้อนก่อนยุค Sentinel-2

Sentinel-1 ใช้เป็น supplementary context เมื่อ optical มี cloud/gap มาก แต่ห้ามแปลผลแทน shoreline โดยไม่มีวิธีที่ validate แล้ว

### Tide

ลำดับความน่าเชื่อถือ:

1. ตารางน้ำทางการ / Hydrographic Department, Royal Thai Navy
2. ThailandTideTables หรือแหล่ง secondary ที่ระบุ station/source ชัดเจน
3. แหล่งอื่นใช้ได้เฉพาะเมื่อ provenance ชัดและมี QA

สำหรับ ThailandTideTables ให้ไล่ URL pattern รายปี/เดือนเหมือนงานปากน้ำแม่กลอง แล้ว cache raw page + source URL + retrieval URL + checksum + QA

**ห้ามใช้ datum offset ของปากน้ำแม่กลอง 2.14 m กับจังหวัดอื่นโดยอัตโนมัติ** ต้องหา station-specific relation ระหว่าง chart datum/LLW กับ MSL ใหม่ทุกครั้ง

ค่า tide จาก published extrema เป็น **predicted/secondary estimate** ไม่ใช่ observed water level หน้าแปลง ต้องระบุไว้เสมอ

### Other free context

ใช้ได้เมื่อมีประโยชน์:

- ERA5 wind / pressure / precipitation
- tropical cyclone tracks
- public DEM
- OpenStreetMap / public basemap
- public coastal structure layers ถ้ามี

แต่ข้อมูลเสริมเหล่านี้ไม่ควรถูกใช้เพื่ออ้างผลเชิงสาเหตุเกินหลักฐาน

## Province configuration

สำหรับจังหวัดใหม่ ให้สร้าง configuration เดียวที่เป็น source of truth เช่น:

```yaml
province_key: krabi
province_th: กระบี่
province_en: Krabi
analysis_crs: EPSG:32647
project_aoi: data/aoi/krabi_project_analysis_aoi.geojson
plots: data/aoi/krabi_project_plots.geojson
coastal_plot_ids: []
non_coastal_plot_ids: []
tide_station:
  name: TBD
  source: TBD
  datum_relation_to_msl_m: TBD
history_start_year: 2017
latest_year: 2026
planting_dates_source: data/project/krabi_planting_evidence.csv
production_project: krabi-coastal-change
```

ถ้าจังหวัดคร่อม UTM zone หรือ AOI กว้างมาก ให้เลือก CRS ที่เหมาะกับพื้นที่จริงและบันทึกเหตุผล

## Workflow

### Phase 1 — AOI and eligibility

1. โหลด plot polygons
2. สร้าง project analysis AOI ที่มี coastal context buffer พอสมควร
3. แยกแปลงที่สัมพันธ์กับ marine shoreline ออกจากแปลงที่อยู่ลึกเข้าไปในคลอง/บก
4. แปลงที่ไม่ติด marine shoreline ห้ามฝืนใส่ใน coastal erosion metric
5. ถ้าเป็น riverbank/canal edge ให้ classify เป็น `BANK_EDGE` / `ZONAL_PROXY_ONLY` และวิเคราะห์แยก

ผลลัพธ์ขั้นต่ำ:

- project plots GeoJSON
- analysis AOI GeoJSON
- eligibility table

### Phase 2 — Satellite scene catalog

สร้าง catalog reproducible โดยเก็บ:

- provider
- collection
- scene_id
- acquisition UTC/Bangkok time
- cloud cover scene/AOI
- bands
- STAC/source URL
- local paths
- QA status
- selection reason

สำหรับ historical context ให้พยายามสร้าง annual record ตั้งแต่ Sentinel-2 เริ่มมีข้อมูล หรือย้อนหลังด้วย Landsat ถ้าจำเป็น

อย่าเลือก scene จากความสวยอย่างเดียว ต้องคำนึง cloud, season, coverage และ tide

### Phase 3 — Tide catalog and tide matching

1. หา tide station ที่เหมาะที่สุดกับจังหวัด/แปลง
2. หา datum relation ของ station นั้นกับ MSL
3. ดึง official hourly prediction ถ้ามี
4. เติม historical gap ด้วย secondary published extrema ถ้าจำเป็น
5. interpolate scene-time tide เฉพาะเมื่อมี before/after extrema ที่เหมาะสม
6. เก็บ source tier และ QA แยกทุก scene
7. เลือก target tide จาก scene set ที่ดีที่สุด แทนการ hardcode จังหวัดก่อนหน้า
8. เลือก annual WATERLINE scene ที่ tide ใกล้ target ที่สุดและผ่าน tolerance

ถ้า historical year มีภาพแต่ tide ไม่ผ่าน ให้ใช้ภาพนั้นเป็น `VISUAL_AND_VEGETATION_CONTEXT_ONLY` ห้ามฝืนใช้ WATERLINE

### Phase 4 — Spectral products

สร้างจาก Sentinel-2 bands จริง ไม่ใช่ generated images:

- RGB: B4/B3/B2
- False vegetation: NIR/Red/Green = B8/B4/B3
- NDVI = (B8-B4)/(B8+B4)
- MNDWI = (B3-B11)/(B3+B11)
- SWIR-NIR-Red composite = B11/B8/B4

สร้าง 2 view อย่างน้อย:

- `focus`: coastal treatment plots
- `full`: whole project AOI

ภาพ raster ที่ใช้ในเว็บต้องเป็น **image-only** ไม่มีข้อความ ชื่อแปลง ลูกศรเหนือ หรือ polygon ฝังในภาพ

### Phase 5 — WATERLINE

ใช้ MNDWI/ocean connectivity method ที่มี QA และสร้าง waterline รายปีเฉพาะปีที่ tide ผ่าน

หลักการ:

- waterline เป็น supporting indicator
- tide matching ลด bias แต่ไม่ใช่ full tide normalization
- อย่าเรียก waterline ว่า surveyed shoreline
- เก็บ threshold method, valid fraction, tide level, tide delta, source resolution และ confidence

### Phase 6 — MANGROVE_EDGE_PROXY

ใช้ NDVI / vegetation mask สร้าง seaward vegetation edge

ต้องเรียก `MANGROVE_EDGE_PROXY` จนกว่าจะ validate ด้วย UAV/field/confusion matrix

ห้ามแปล NDVI edge movement ว่า:

- land accretion จริง
- sediment accumulation จริง
- mangrove area confirmed

โดยไม่มี validation เพิ่ม

### Phase 7 — Transects

สร้าง transects ที่ anchored กับ reference coast และใช้ geometry ชุดเดียวกันเปรียบเทียบทุกปี

สำหรับแต่ละ intersection คำนวณ position ตาม convention เดียวกัน เช่น positive = seaward

metrics หลัก:

- NSM
- EPR
- LRR
- SCE

screening threshold ควรสอดคล้องกับ effective resolution ของ analysis ไม่ใช่ copy 20 m แบบตายตัว ถ้า analysis ยังอยู่บน 20 m grid สามารถใช้ ±20 m เป็น conservative screening band ได้

### Phase 8 — Candidate controls

สร้าง candidate control transects ใกล้แต่ละ treatment plot แต่ต้อง mark ว่า `CANDIDATE_UNVERIFIED` จนกว่าจะตรวจ:

- coastal structures
- dredging
- reclamation
- other planting
- different creek/estuary geomorphology
- major land-use change

ห้ามเรียก treatment-control difference ว่า causal effect ก่อน verify confounders

### Phase 9 — Pre-planting history

เป้าหมายคือถามว่า:

> ก่อนช่วงปลูก มีสัญญาณถอยเข้าฝั่งมากกว่าช่วงล่าสุดหรือไม่?

แบ่งช่วงตาม evidence จริง ไม่ใช่ตามปีที่อยากได้

ถ้ามีเพียง planting completion date แต่ไม่มี planting start date:

- scene ก่อน completion = `BEFORE_COMPLETION_START_UNKNOWN`
- ห้ามเรียก `confirmed pre-plant`
- scene หลัง completion = `CONFIRMED_POST_COMPLETION`

เปรียบเทียบ historical vs recent ด้วย:

- class counts: `APPARENT_LANDWARD`, `WITHIN_THRESHOLD`, `APPARENT_SEAWARD`
- median NSM
- median LRR
- per-plot breakdown

### Phase 10 — Planting-aware analysis

เมื่อมี planting date evidence ให้คำนวณใหม่โดยผูก scene กับ plot timing

ขั้นต่ำ:

- last observation before completion
- first confirmed post-completion observation
- latest confirmed post-completion observation
- days from completion
- post-completion WATERLINE change
- post-completion MANGROVE_EDGE_PROXY change
- class counts per plot

ถ้ามี post-completion annual observations เพียง 2 ปี ให้ confidence = LOW และห้ามสร้าง causal conclusion

### Phase 11 — UAV / field validation

ถ้ามีโดรน ใช้เพื่อยกระดับหลักฐาน ไม่ใช่ requirement สำหรับเริ่มงาน

เป้าหมาย:

- validate mangrove seaward edge
- derive `BANK_EDGE` / surveyed edge
- inspect hotspots flagged by satellite
- verify structures and controls
- compare same-season / similar-tide acquisitions if possible

## Web dashboard requirements

เว็บ production ต้องเป็น evidence dashboard ไม่ใช่แค่ gallery

### Required sections

1. **Latest Finding / Executive highlight**
   - ข้อสรุปล่าสุดใหญ่และเห็นทันที
   - ระบุ plot ที่มี planting date verified
   - ระบุสิ่งที่พูดได้ / ยังพูดไม่ได้

2. **Before/After multispectral slider**
   - select year before/after
   - RGB
   - False vegetation
   - NDVI
   - MNDWI
   - SWIR
   - tide metadata
   - scene role (`WATERLINE` vs visual-only)

3. **SVG plot overlays rendered by web**
   - plot boundaries
   - plot labels
   - analysis extent if useful
   - toggle on/off
   - **ห้าม bake labels/boundaries ลง raster**

4. **Zoom + pan**
   - zoom 100–300% หรือมากกว่าถ้าจำเป็น
   - zoom in / zoom out / reset
   - pan left/right/up/down by dragging image when zoom >100%
   - Before/After raster และ SVG overlay ต้อง zoom/pan ด้วย transform เดียวกัน
   - divider handle ต้องลากแยกจาก pan gesture
   - reset ต้องคืนทั้ง zoom และ pan

5. **Planting evidence timeline**
   - selected scene before completion
   - planting completion date
   - first post-completion scene
   - latest scene
   - days after completion

6. **Per-plot result**
   - WATERLINE
   - MANGROVE_EDGE_PROXY
   - transect counts
   - controls status

7. **Evidence ladder / limitations**
   - satellite history
   - tide-aware screening
   - planting timing
   - UAV/field validation
   - verified controls

### Internal link rule

ถ้า production HTML ใช้ `<base href>` ชี้ CDN ห้ามปล่อย anchor link `#section` ให้ browser resolve ไป CDN directory

ให้ intercept internal anchors หรือใช้ JS `scrollIntoView()` เพื่อให้ลิงก์ภายในยังอยู่บน Vercel production domain

### Font rule

ข้อความไทยต้องเป็น HTML/SVG web text ไม่ใช่ข้อความ rasterized ลงภาพ

ใช้ Thai-capable font เช่น:

- IBM Plex Sans Thai
- Noto Sans Thai

ไม่ commit/share font binaries ถ้าไม่จำเป็น; prefer web font or system fallback

## Production deployment pattern

ใช้ branch หลักของงานจังหวัดนั้นเป็น source แล้ว:

1. run scientific/data validation
2. run TypeScript/build
3. publish immutable production bundle branch
4. deploy to Vercel production project
5. verify deployment = `READY`
6. verify production alias returns HTTP 200
7. verify title/meta/base commit point to latest immutable bundle

เมื่อผู้ใช้สั่ง “อะไรที่แก้แล้ว deploy เลย” ให้ทำ deployment ต่อเนื่องหลัง validation ผ่าน ไม่ต้องรอถามซ้ำ

## Claim guard

### Allowed language at screening level

ใช้รูปแบบเช่น:

> การวิเคราะห์ภาพดาวเทียมที่คัดตามระดับน้ำไม่พบสัญญาณการถอยร่นขนาดใหญ่เป็นวงกว้างในช่วงข้อมูลที่มี และพบสัญญาณการเปลี่ยนแปลงของขอบพืชในบางบริเวณ อย่างไรก็ตาม ผลดังกล่าวยังเป็น satellite screening และยังไม่สามารถระบุได้ว่าการเปลี่ยนแปลงเกิดจากการปลูกป่าชายเลน

ถ้ามี verified planting completion dates:

> หลังวันปลูกเสร็จที่ยืนยันแล้ว ภาพที่ติดตามในช่วงถัดมาไม่พบการถอยร่นเป็นวงกว้าง / พบสัญญาณเฉพาะตำแหน่ง ตามข้อมูลที่วิเคราะห์ได้

### Not allowed without stronger evidence

ห้ามเขียนว่า:

- การปลูกป่าหยุดการกัดเซาะแล้ว
- การปลูกป่าลดการกัดเซาะได้ X เมตร/ปี
- ขอบพืช +20 m = แผ่นดินงอก 20 m
- ป่าดักตะกอนได้ X
- ป่าลดคลื่น / ป้องกันพายุได้ X
- treatment-control difference = causal effect

เว้นแต่มีข้อมูลและวิธีที่รองรับข้อกล่าวนั้นจริง

## Evidence levels

ใช้สถานะที่สื่อความหมายชัด เช่น:

- `SATELLITE_SCREENING`
- `TIDE_AWARE_SCREENING`
- `TIDE_AWARE_PREPLANTING_CONTEXT`
- `PARTIAL_PLANTING_COMPLETION_DATES_VERIFIED`
- `UAV_VALIDATED_EDGE`
- `VERIFIED_CONTROL_COMPARISON`

`EROSION EFFECT: NOT_DEMONSTRATED` ต้องคงอยู่จนกว่าหลักฐานเชิงสาเหตุเพียงพอ

## QA gates

ก่อน merge/deploy ตรวจอย่างน้อย:

- AOI/plots geometry valid
- no forced marine analysis for non-coastal plots
- catalog covers requested years
- every accepted WATERLINE scene has tide datum + tide level + source tier
- secondary tide validation passes where used
- image files exist for every advertised year/mode/view
- SVG overlays exist and align with raster
- transect count stable across periods
- all metric rows carry confidence
- planting dates never inferred beyond source evidence
- claim status not accidentally promoted
- TypeScript build passes
- production bundle contains JSON/GeoJSON/assets referenced by UI
- Vercel production status `READY`

## Output structure recommendation

```text
data/
  aoi/
    <province>_project_plots.geojson
    <province>_project_analysis_aoi.geojson
  catalog/
    <province>_sentinel2_history.csv
  tide/
    <province>/
      <station>_extrema.csv
      <station>_validation.json
  project/
    <province>_planting_evidence.csv
  processed/
    <province>_tide_aware/
    <province>_preplanting_history/
    <province>_planting_aware/
web/public/data/
  <province>_history/
    summary.json
    visuals/
    overlay/
```

## Expected user-facing summary for each province

เมื่อทำเสร็จ ให้สรุป 5 เรื่องเท่านั้นก่อน แล้วค่อยลงรายละเอียดถ้าผู้ใช้ถาม:

1. ย้อนหลังได้ถึงปีไหน
2. ปีไหนมี tide-aware WATERLINE จริง
3. ก่อนปลูกเคยมีสัญญาณถอยหรือไม่
4. หลังปลูกเสร็จที่ยืนยันแล้วเป็นอย่างไร
5. ตอนนี้เคลมได้ไกลแค่ไหน / ยังขาดอะไร

## Samut Songkhram reference implementation

ใช้ไฟล์/แนวคิดเหล่านี้เป็น reference แต่ parameterize ใหม่:

- `scripts/build_preplanting_coastal_history.py`
- `scripts/build_tide_aware_project_edges.py`
- `scripts/build_secondary_mae_klong_tide_catalog.py`
- `scripts/apply_samut_songkhram_planting_evidence.py`
- `web/src/PreplantingHistoryDashboardV2.tsx`
- `web/src/PlotOverlayInjector.tsx`
- `web/src/PlantingEvidenceInjector.tsx`
- `web/src/preplantingSpectral.css`
- `web/src/plotOverlay.css`
- `web/src/plantingEvidence.css`

อย่า hardcode `samut_songkhram`, `Pak Nam Mae Klong`, plot IDs, 2.14 m datum offset หรือ production domain ลง implementation จังหวัดใหม่ ให้ย้ายไป config / province-specific data

## Definition of done

จังหวัดหนึ่งถือว่า “เสร็จระดับเดียวกับ Samut Songkhram” เมื่อ:

- มี annual satellite history ที่ reproducible
- tide metadata ถูกเชื่อมและ WATERLINE years ผ่าน QA
- WATERLINE + MANGROVE_EDGE_PROXY + transects + period metrics ถูกสร้าง
- planting date evidence ที่มีถูกนำเข้าจริง
- control status แสดงตรงตามระดับ validation
- เว็บมี multispectral slider + plot SVG overlay + zoom + pan
- latest finding ถูก highlight ชัด
- scientific limitations แสดงบนเว็บ
- production deployment พร้อม URL ใช้งานจริง
- claim guard ยังป้องกัน overclaim

เมื่อผู้ใช้สั่งจังหวัดใหม่ เช่น “ทำกระบี่แบบสมุทรสงคราม” ให้เปิดไฟล์นี้ก่อน แล้วเดิน workflow ต่อจาก template โดยไม่เริ่มโครงสร้างใหม่
