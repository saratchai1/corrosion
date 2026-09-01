---
name: thailand-mangrove-coastal-erosion-province
description: Reusable workflow for building a free-data, tide-aware mangrove coastal-erosion evidence pipeline, multispectral history dashboard, and optional high-resolution drone evidence page for any Thai province, based on the validated Samut Songkhram implementation.
---

# Thailand Mangrove Coastal-Erosion Province Skill

## Purpose

ใช้ skill นี้เมื่อผู้ใช้สั่งให้ทำจังหวัดใหม่ในลักษณะเดียวกับงานสมุทรสงคราม เช่น ระยอง กระบี่ พังงา ภูเก็ต ระนอง สตูล สุราษฎร์ธานี หรือจังหวัดชายฝั่งอื่น ๆ โดยเป้าหมายคือสร้างหลักฐานจาก **ข้อมูลฟรีบนอินเทอร์เน็ต + ข้อมูลโครงการที่มีอยู่แล้ว + โดรน/ภาคสนามที่ต้องทำตามปกติ** เพื่อประเมินว่าแนวชายฝั่งก่อนและหลังการปลูกป่าชายเลนเปลี่ยนอย่างไร และหลักฐานไปได้ไกลแค่ไหนในการสนับสนุนคำกล่าวเรื่องการลดการกัดเซาะ

งานต้องจบเป็น pipeline ที่ทำซ้ำได้, มี QA/claim guard, มีผลลัพธ์ machine-readable และมีเว็บ production ที่คนทั่วไปอ่านเข้าใจได้

## Golden rules

### 1. อย่าเริ่มใหม่จากศูนย์

ใช้โครงสร้างและ pattern จาก Samut Songkhram ใน repo `saratchai1/corrosion` เป็น template แล้ว parameterize จังหวัดใหม่ เช่น province key, AOI, plot IDs, tide station, datum, planting dates, time range, output path, drone source และ production project name

### 2. อย่าทับของเดิมที่ดีอยู่แล้ว

การเพิ่ม evidence ใหม่ต้องเป็น **additive change** ก่อนเป็น default

- หน้า multispectral history ที่ใช้งานดีแล้วต้องคงอยู่เป็นหน้าหลัก
- ถ้าเพิ่ม Drone / LiDAR / field evidence ให้เพิ่มเป็นหน้าใหม่หรือ evidence layer ใหม่
- ห้ามแทรก panel ใหม่ขนาดใหญ่ก่อน slider เดิมจน UX หลักถูกกลบ
- ก่อน merge ให้เทียบกับ production ก่อนหน้าและตรวจว่า feature เดิมยังอยู่ครบ
- ถ้าผู้ใช้บอกว่า “เวอร์ชันก่อนหน้าดีแล้ว” ให้รักษา structure/interaction เดิมก่อนเพิ่มของใหม่

### 3. แยกหลักฐานคนละระดับให้ชัด

- Sentinel-2 history = multi-year temporal screening
- tide-aware scene = waterline supporting evidence
- planting dates = intervention timing evidence
- drone orthomosaic 1 epoch = high-resolution spatial baseline
- repeat drone = high-resolution change evidence
- verified control = comparative evidence

อย่าเอาหลักฐานคนละระดับมารวมจนผู้ใช้ตีความว่าความละเอียดสูง = causal proof

### 4. ห้าม copy ค่าจังหวัดก่อนหน้าโดยไม่ตรวจใหม่

โดยเฉพาะ:

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
- drone flight date
- GSD / coverage threshold interpretation

## Required user inputs

ถ้ามี ให้ขอ/ใช้ข้อมูลเหล่านี้ก่อน แต่ **อย่าหยุดงานเพียงเพราะยังไม่ครบ** ให้ทำจากข้อมูลฟรีที่หาได้ก่อนและระบุช่องว่างไว้

1. ขอบแปลงจริง: KMZ/KML/GeoJSON/Shapefile
2. รหัสแปลงและจังหวัด
3. วันเริ่มปลูก / วันปลูกเสร็จ / วันปลูกซ่อม อย่างน้อยเดือน-ปี
4. พื้นที่ปลูกจริง (rai) และพื้นที่ตาม PDD ถ้ามี
5. รูป/orthomosaic/flight log จากโดรน ถ้ามี
6. GCP / RTK / photogrammetry project metadata ถ้ามี
7. ข้อมูลโครงสร้างชายฝั่ง: ไม้ไผ่ เขื่อนหิน geotube seawall ฯลฯ
8. พื้นที่ใกล้เคียงที่รู้ว่าไม่ได้ปลูก ถ้ามี

ถ้าผู้ใช้ส่ง screenshot ตารางวันปลูก ให้เก็บเป็น evidence record แยกจากข้อมูลที่อนุมาน ห้ามเดาวันเริ่มปลูกจากวันปลูกเสร็จ

## Large drone / GeoTIFF input rule

ถ้า orthomosaic รวมหลาย GB:

- เก็บ raw GeoTIFF ไว้ใน Google Drive / Shared Drive ได้
- **Shared with me ใช้ได้ ไม่จำเป็นต้องย้ายเข้า My Drive** ถ้าสิทธิ์อ่านไฟล์ทำงานจริง
- ถ้าต้องการหาไฟล์ง่าย ให้ใช้ Drive shortcut แทนการ copy 10+ GB ซ้ำ
- อย่า commit raw `.tif` หลาย GB เข้า GitHub
- อย่า serve raw GeoTIFF ใหญ่จาก Vercel
- เก็บใน GitHub เฉพาะ manifest, metadata, QA, footprint, vector และ lightweight preview/derived web assets

ชื่อ folder/date จาก Drive เป็นเพียง evidence label จนกว่าจะยืนยันว่าเป็น acquisition date จาก flight log, EXIF, Pix4D/Metashape project, RTK/GCP record หรือ project document

ตัวอย่างสถานะ:

- `FOLDER_LABEL_UNVERIFIED_AS_FLIGHT_DATE`
- `FLIGHT_DATE_VERIFIED`

ห้ามเปลี่ยน folder label เป็น verified flight date โดยอัตโนมัติ

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

สำหรับ ThailandTideTables ให้ไล่ URL pattern รายปี/เดือน แล้ว cache raw page + source URL + retrieval URL + checksum + QA

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
drone:
  enabled: false
  drive_folder_id: null
  date_status: UNVERIFIED
  source_manifest: data/project/krabi_drone_drive_manifest.csv
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

### Phase 11 — Drone orthomosaic ingest and QA

ถ้ามี orthomosaic ให้ตรวจ metadata ก่อนเอาไปตีความ

ขั้นต่ำต่อไฟล์:

- plot_id
- Drive file id / source title
- source size
- CRS
- width / height
- band count
- transform / bounds
- GSD
- nodata / alpha / valid mask
- bbox overlap กับ plot polygon
- valid imagery fraction ภายใน plot
- folder/date evidence status

แยก QA ออกเป็นสองเรื่อง:

1. **Georeference QA** — CRS, transform, spatial overlap ถูกหรือไม่
2. **Imagery coverage QA** — ใน polygon มี valid pixels มากเท่าไร

ห้ามตีความ NoData ที่ขอบภาพว่า georeference fail ถ้าพิกัดถูกต้อง

default classification ที่ใช้ได้เป็น starting point:

- `COMPLETE_GE_95PCT` = valid imagery ≥95%
- `PARTIAL_USABLE_90_TO_95PCT` = 90–<95%
- `INSUFFICIENT_LT_90PCT` = <90%

threshold ปรับได้ตามชนิดข้อมูล แต่ต้องบันทึกไว้ใน config/QA

ถ้าไฟล์ใหญ่มาก ให้ workflow ดาวน์โหลดทีละไฟล์ → inspect/build preview → ลบ raw local copy → ทำไฟล์ถัดไป เพื่อลด runner storage

ถ้า raster เป็น `RGB + Alpha` 4 bands และไม่มี NIR:

- ใช้ดูขอบแปลง/ขอบพืช/ขอบตลิ่งได้
- **ห้ามคำนวณ drone NDVI**
- ระบุ `nir_band_present: false` และ `drone_ndvi_supported: false`

ถ้ามี orthomosaic เพียง 1 epoch:

- เรียก `HIGH_RESOLUTION_BASELINE`
- ใช้ cross-check Sentinel-2 edge / hotspot / structures
- ห้ามคำนวณ drone-derived erosion rate
- ห้ามอ้าง before-after จากโดรนจนกว่าจะมี repeat epoch

### Phase 12 — UAV / field validation

เมื่อมี repeat drone หรือภาคสนาม ให้ยกระดับหลักฐาน:

- validate mangrove seaward edge
- derive `BANK_EDGE` / surveyed edge
- inspect hotspots flagged by satellite
- verify structures and controls
- compare same-season / similar-tide acquisitions if possible
- preserve flight metadata and uncertainty

## Web information architecture

### Primary navigation — ใช้ 5 ปลายทางนี้เป็นมาตรฐาน

ลำดับและชื่อเมนูควรเหมือนกันทุกหน้าหลัก:

1. `หลักฐานย้อนหลัง`
2. `ผล 2023–2026` หรือช่วงปีล่าสุดของจังหวัดนั้น
3. `ภาพโดรน HR` — แสดงเมื่อมีข้อมูลโดรน
4. `รายงาน 9 แปลง` — เปลี่ยนจำนวนตามจังหวัด
5. `แผนที่ 10 ปี`

ถ้าจังหวัดไม่มีโดรน ให้ซ่อนหน้า Drone แต่ **อย่าเปลี่ยนความหมายของหน้าอื่นเพื่อชดเชย**

### หน้าที่ของแต่ละหน้า

#### A. หลักฐานย้อนหลัง — default landing page

นี่คือหน้าหลักและต้องรักษา UX ที่พิสูจน์แล้วว่าดี:

- history 2017–latest หรือช่วงที่ข้อมูลรองรับ
- multispectral before/after slider
- เลือก Before / After ได้หลายปี
- quick pairs จาก config
- RGB / False vegetation / NDVI / MNDWI / SWIR
- focus/full view
- web SVG plot overlay
- zoom + pan
- planting-aware highlight / latest finding

**ห้ามเอา Drone HR panel ขนาดใหญ่ไปแทรกก่อน slider หน้านี้**

#### B. ผลช่วงล่าสุด

เน้น executive interpretation:

- latest finding
- tide-aware results
- what is known / unknown
- evidence ladder
- per-plot result
- scene/tide QA

#### C. ภาพโดรน HR

เป็น standalone page แยกจาก history:

- plot selector
- orthomosaic preview
- compare Drone ↔ selected Sentinel-2 on same geographic extent
- project boundary SVG
- WATERLINE / MANGROVE_EDGE_PROXY overlay
- zoom + pan
- coverage/GSD/CRS QA
- flight-date status
- explicit one-epoch guard

#### D. รายงานรายแปลง

สรุป project-level + per-plot metrics, map, controls, planting timing, limitations

#### E. แผนที่หลายปี

interactive spatial explorer สำหรับ annual/historical imagery และ transects ไม่ควรแทน multispectral evidence page

## Multispectral slider requirements

1. select year before/after จาก scene list จริง
2. quick pair presets ควร derive จาก config / meaningful periods
3. RGB
4. False vegetation
5. NDVI
6. MNDWI
7. SWIR
8. tide metadata
9. scene role (`WATERLINE` vs visual-only)
10. focus/full view

### SVG plot overlays rendered by web

- plot boundaries
- plot labels
- analysis extent ถ้ามีประโยชน์
- toggle on/off
- **ห้าม bake labels/boundaries ลง raster**

### Zoom + pan

- zoom 100–300% หรือมากกว่าถ้าจำเป็น
- zoom in / zoom out / reset
- pan left/right/up/down by dragging image when zoom >100%
- Before/After raster และ SVG overlay ต้อง zoom/pan ด้วย transform เดียวกัน
- divider handle ต้องลากแยกจาก pan gesture
- reset ต้องคืนทั้ง zoom และ pan

## Planting evidence timeline

แสดงอย่างน้อย:

- selected scene before completion
- planting completion date
- first post-completion scene
- latest scene
- days after completion
- source/status ของวันปลูก

## Evidence ladder / limitations

อย่างน้อย:

1. satellite history
2. tide-aware screening
3. planting timing
4. UAV/field validation
5. verified controls

## Link and navigation rules

### Internal anchor rule

ถ้า production HTML ใช้ `<base href>` ชี้ CDN ห้ามปล่อย anchor link `#section` ให้ browser resolve ไป CDN directory

ให้ intercept internal anchors หรือใช้ JS `scrollIntoView()` เพื่อให้ลิงก์ภายในยังอยู่บน Vercel production domain

### Evidence-file link audit

ก่อน deploy:

- ตรวจ `href="data/..."` ทุกตัวว่าปลายทางมีจริงใน `web/public`
- ตรวจไฟล์ JSON/CSV/GeoJSON/SVG ที่ UI อ้างถึง
- ห้ามมี raw `href="#"` ที่ไม่มี target
- เมนูหลักทุกหน้าต้องใช้ชื่อ/ลำดับเดียวกัน
- active state ต้องตรงกับหน้าปัจจุบัน
- ห้ามมีปุ่มย้อนกลับซ้ำกับ navigation โดยไม่จำเป็น

### Narrow sidebar rule

ถ้า page ใช้ sidebar แคบ เช่น map explorer:

- เมนู 5 รายการควร wrap/grid ได้
- ห้ามบีบปุ่มจนอ่านข้อความไม่ได้
- mobile/tablet ต้องไม่ overflow

## Font rule

ข้อความไทยต้องเป็น HTML/SVG web text ไม่ใช่ข้อความ rasterized ลงภาพ

ใช้ Thai-capable font เช่น:

- IBM Plex Sans Thai
- Noto Sans Thai

ไม่ commit/share font binaries ถ้าไม่จำเป็น; prefer web font or system fallback

## Production deployment pattern

ใช้ branch หลักของงานจังหวัดนั้นเป็น source แล้ว:

1. run scientific/data validation
2. run TypeScript/build
3. publish immutable production bundle branch เช่น `production-<province>`
4. pin production HTML `<base href>` ไปที่ immutable bundle commit
5. deploy to Vercel production project
6. verify deployment = `READY`
7. verify canonical production alias returns HTTP 200
8. verify title/meta/base commit point to latest immutable bundle
9. verify key data assets return HTTP 200

เมื่อผู้ใช้สั่ง “อะไรที่แก้แล้ว deploy เลย” ให้ทำ deployment ต่อเนื่องหลัง validation ผ่าน ไม่ต้องรอถามซ้ำ

## Claim guard

### Allowed language at screening level

ใช้รูปแบบเช่น:

> การวิเคราะห์ภาพดาวเทียมที่คัดตามระดับน้ำไม่พบสัญญาณการถอยร่นขนาดใหญ่เป็นวงกว้างในช่วงข้อมูลที่มี และพบสัญญาณการเปลี่ยนแปลงของขอบพืชในบางบริเวณ อย่างไรก็ตาม ผลดังกล่าวยังเป็น satellite screening และยังไม่สามารถระบุได้ว่าการเปลี่ยนแปลงเกิดจากการปลูกป่าชายเลน

ถ้ามี verified planting completion dates:

> หลังวันปลูกเสร็จที่ยืนยันแล้ว ภาพที่ติดตามในช่วงถัดมาไม่พบการถอยร่นเป็นวงกว้าง / พบสัญญาณเฉพาะตำแหน่ง ตามข้อมูลที่วิเคราะห์ได้

ถ้ามี drone 1 epoch:

> ภาพโดรนความละเอียดสูงใช้เป็น baseline เชิงพื้นที่และใช้ตรวจตำแหน่งขอบแปลง/ขอบพืช/ขอบตลิ่งได้ละเอียดขึ้น แต่ยังไม่ใช่หลักฐานการเปลี่ยนแปลงตามเวลาเพราะยังไม่มีภาพโดรนซ้ำ

### Not allowed without stronger evidence

ห้ามเขียนว่า:

- การปลูกป่าหยุดการกัดเซาะแล้ว
- การปลูกป่าลดการกัดเซาะได้ X เมตร/ปี
- ขอบพืช +20 m = แผ่นดินงอก 20 m
- ป่าดักตะกอนได้ X
- ป่าลดคลื่น / ป้องกันพายุได้ X
- treatment-control difference = causal effect
- drone orthomosaic 1 epoch แสดงอัตรากัดเซาะ

เว้นแต่มีข้อมูลและวิธีที่รองรับข้อกล่าวนั้นจริง

## Evidence levels

ใช้สถานะที่สื่อความหมายชัด เช่น:

- `SATELLITE_SCREENING`
- `TIDE_AWARE_SCREENING`
- `TIDE_AWARE_PREPLANTING_CONTEXT`
- `PARTIAL_PLANTING_COMPLETION_DATES_VERIFIED`
- `HIGH_RESOLUTION_BASELINE`
- `UAV_VALIDATED_EDGE`
- `REPEAT_UAV_CHANGE_EVIDENCE`
- `VERIFIED_CONTROL_COMPARISON`

`EROSION EFFECT: NOT_DEMONSTRATED` ต้องคงอยู่จนกว่าหลักฐานเชิงสาเหตุเพียงพอ

## QA gates

ก่อน merge/deploy ตรวจอย่างน้อย:

### Science/data

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

### Drone

- raw source is referenced but not committed to normal Git history
- all advertised plots have metadata records
- georeference QA and coverage QA are separate
- CRS is plausible for province and agrees with plot geometry
- GSD is recorded
- valid imagery fraction is recorded
- band count is recorded
- RGB-only data cannot silently produce NDVI
- folder date cannot silently become verified flight date
- one epoch cannot silently become change-rate evidence
- all lightweight preview/alignment/overlay assets exist

### Web / regression

- original multispectral history slider still exists
- all intended years remain selectable
- all 5 spectral modes remain selectable
- SVG plot overlay toggle works
- zoom works
- pan works when zoomed
- divider still works independently from pan
- Drone HR is a separate page, not injected before history slider
- main navigation labels/order are consistent
- no duplicate navigation bars
- evidence/data links resolve
- Thai font renders correctly
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
    <province>_drone_drive_manifest.csv
  processed/
    <province>_tide_aware/
    <province>_preplanting_history/
    <province>_planting_aware/
    <province>_drone/
web/public/data/
  <province>_history/
    summary.json
    visuals/
    overlay/
  <province>_drone/
    summary.json
    previews/
    sentinel_alignment/
    alignment_overlay/
```

## Expected user-facing summary for each province

เมื่อทำเสร็จ ให้สรุป 5 เรื่องก่อน แล้วค่อยลงรายละเอียดถ้าผู้ใช้ถาม:

1. ย้อนหลังได้ถึงปีไหน
2. ปีไหนมี tide-aware WATERLINE จริง
3. ก่อนปลูกเคยมีสัญญาณถอยหรือไม่
4. หลังปลูกเสร็จที่ยืนยันแล้วเป็นอย่างไร
5. ตอนนี้เคลมได้ไกลแค่ไหน / ยังขาดอะไร

ถ้ามี Drone HR เพิ่มบรรทัดสั้น ๆ ว่า:

- มี high-resolution baseline กี่แปลง, GSD range เท่าไร, coverage มี caveat ที่แปลงใด และเป็น 1 epoch หรือ repeat epoch

## Samut Songkhram reference implementation

ใช้ไฟล์/แนวคิดเหล่านี้เป็น reference แต่ parameterize ใหม่:

### Core science

- `scripts/build_preplanting_coastal_history.py`
- `scripts/build_tide_aware_project_edges.py`
- `scripts/build_secondary_mae_klong_tide_catalog.py`
- `scripts/apply_samut_songkhram_planting_evidence.py`

### History web

- `web/src/PreplantingHistoryDashboardV2.tsx`
- `web/src/PlotOverlayInjector.tsx`
- `web/src/PlantingEvidenceInjector.tsx`
- `web/src/preplantingSpectral.css`
- `web/src/plotOverlay.css`
- `web/src/plantingEvidence.css`

### Drone baseline

- `scripts/inspect_samut_songkhram_drone_orthomosaic.py`
- `scripts/normalize_samut_songkhram_drone_qa.py`
- `scripts/aggregate_samut_songkhram_drone_inventory.py`
- `scripts/build_drone_sentinel_alignment_v2.py`
- `web/src/DroneBaselinePage.tsx`
- `web/src/DroneBaselineInjector.tsx`
- `web/src/droneBaseline.css`
- `.github/workflows/samut-songkhram-drone-drive-ingest.yml`
- `.github/workflows/samut-songkhram-drone-web.yml`

### Navigation / deployment

- `web/src/App.tsx`
- `web/src/navigation.css`
- `.github/workflows/build-production-web-artifact.yml`

อย่า hardcode `samut_songkhram`, `Pak Nam Mae Klong`, plot IDs, 2.14 m datum offset, 2023–2026, 9 plots หรือ production domain ลง implementation จังหวัดใหม่ ให้ย้ายไป config / province-specific data

## Recommended branch strategy for a new province

1. เริ่มจาก branch/template ที่มี web components และ workflow ที่ validate แล้ว
2. สร้าง `data/<province>-...` หรือ `feature/<province>-...` สำหรับ data pipeline
3. parameterize province config ก่อนแก้ component
4. reuse generic component ให้มากที่สุด
5. province-specific string/plot/tide/date อยู่ใน data/config ไม่ใช่ hardcode ใน React
6. merge scientific outputs ก่อนหรือพร้อม web assets
7. สร้าง production bundle branch แยกจังหวัด
8. deploy Vercel project แยกจังหวัด

## Definition of done

จังหวัดหนึ่งถือว่า “เสร็จระดับเดียวกับ Samut Songkhram” เมื่อ:

- มี annual satellite history ที่ reproducible
- tide metadata ถูกเชื่อมและ WATERLINE years ผ่าน QA
- WATERLINE + MANGROVE_EDGE_PROXY + transects + period metrics ถูกสร้าง
- planting date evidence ที่มีถูกนำเข้าจริง
- control status แสดงตรงตามระดับ validation
- หน้า `หลักฐานย้อนหลัง` เป็น default และ multispectral slider เดิมยังอยู่ครบ
- เว็บมี plot SVG overlay + zoom + pan
- latest finding ถูก highlight ชัด
- ถ้ามี Drone HR: raw GeoTIFF ผ่าน metadata/georeference/coverage QA และถูกแยกเป็นหน้า standalone
- ถ้ามี Drone HR 1 epoch: เว็บระบุชัดว่าเป็น baseline ไม่ใช่ erosion-rate time series
- navigation ทั้งเว็บสม่ำเสมอและไม่งง
- evidence/data links ผ่าน audit
- scientific limitations แสดงบนเว็บ
- production deployment พร้อม URL ใช้งานจริง
- claim guard ยังป้องกัน overclaim
- ไม่มี regression ที่ทำให้ feature ที่ดีอยู่แล้วหายไป

เมื่อผู้ใช้สั่งจังหวัดใหม่ เช่น “ทำกระบี่แบบสมุทรสงคราม” หรือ “ทำสุราษฎร์ธานีแบบสมุทรสงคราม” ให้เปิดไฟล์นี้ก่อน แล้วเดิน workflow ต่อจาก template โดยไม่เริ่มโครงสร้างใหม่ และถ้ามี evidence ใหม่ให้เพิ่มแบบ additive ไม่ทับหน้าเดิม