---
name: coastal-erosion-accretion
description: Reusable, tide-aware workflow for analyzing coastal erosion, apparent shoreline accretion, landward/seaward shoreline movement, mangrove-edge change, and land/water change from real satellite, tide, UAV, and field data. Explicitly excludes super-resolution from quantitative shoreline metrics.
---

# Coastal Erosion / Accretion Skill

## Purpose

ใช้ skill นี้เมื่อผู้ใช้ต้องการวิเคราะห์ **การกัดเซาะชายฝั่ง / ดินงอก / แนวชายฝั่งเปลี่ยน / land gain-loss / mangrove edge advance-retreat** จากข้อมูลจริง โดยเน้น workflow ที่ทำซ้ำได้ ตรวจสอบย้อนกลับได้ และไม่อ้างเกินหลักฐาน

เหมาะกับงาน เช่น:

- วิเคราะห์แนวชายฝั่งย้อนหลังหลายปี
- เปรียบเทียบก่อน–หลังช่วงปลูกป่าชายเลน
- หาแนวโน้มถอยเข้าฝั่งหรือรุกออกทะเล
- ประเมิน apparent erosion / apparent accretion
- ทำ WATERLINE และ MANGROVE_EDGE_PROXY
- ทำ transect metrics แบบ DSAS-like
- คัดภาพดาวเทียมให้ระดับน้ำใกล้เคียงกัน
- ทำ land/water change map สำหรับ dashboard
- หา hotspot ที่ควรตรวจด้วยโดรนหรือภาคสนาม
- สร้าง machine-readable evidence เพื่อเอาไปต่อเว็บ/รายงาน

คำว่า **ดินงอก** ในผลจากดาวเทียมต้องใช้ด้วยความระมัดระวัง: การที่ waterline หรือ vegetation edge ขยับออกทะเลยังไม่เท่ากับยืนยันการสะสมตะกอนหรือระดับพื้นดินสูงขึ้นจริง จนกว่าจะมี elevation/survey/UAV/field evidence รองรับ

---

# Hard boundary: this is NOT a super-resolution skill

## 1. ห้ามใช้ Super Resolution เป็นฐานวัดระยะหรือพื้นที่

ผลเชิงปริมาณของ skill นี้ต้องมาจาก **native analytical data** เท่านั้น

ห้ามใช้ output จาก:

- `skills/sentinel-2-super-resolution/SKILL.md`
- LDSR-S2 / OpenSR
- AI sharpening
- generative enhancement
- interpolated 2.5 m visual output

เพื่อ:

- extract shoreline
- วัด NSM/EPR/LRR/SCE
- วัด land gain/loss
- วัด mangrove edge movement
- เพิ่ม confidence ของ geometry

Super-resolution ใช้ได้เฉพาะ **visual comparison layer** แยกต่างหาก และต้องไม่เปลี่ยน source resolution / uncertainty ของ quantitative result

## 2. ห้ามใช้ image generator

ภาพและ metric ต้องมาจาก raster/vector จริง เช่น Sentinel-2, Landsat, Sentinel-1, UAV orthomosaic, survey หรือ field mapping เท่านั้น

## 3. ห้ามเรียก apparent seaward movement ว่า confirmed sediment accretion โดยอัตโนมัติ

แยก terminology ดังนี้:

- `APPARENT_SEAWARD_WATERLINE_CHANGE` = waterline ขยับออกทะเลเมื่อเทียบภาพที่ tide ผ่าน QA
- `MANGROVE_EDGE_ADVANCE_PROXY` = ขอบพืช proxy ขยับออกทะเล
- `APPARENT_ACCRETION` = หลักฐานเชิงพื้นที่บ่งชี้การงอก แต่ยังไม่ยืนยัน elevation/sediment process
- `CONFIRMED_ACCRETION` = ต้องมีหลักฐานเสริม เช่น survey elevation, repeat UAV surface, RTK profile, bathymetry/topography หรือ field verification ที่เพียงพอ

เช่นเดียวกัน waterline ถอยเข้าฝั่งไม่ควรถูกเรียกว่า confirmed erosion หาก tide/season/geomorphology ยังควบคุมไม่ดี

---

# Evidence model

แยก shoreline indicator อย่างน้อย 3 ประเภท:

1. `WATERLINE`
   - ขอบน้ำ ณ เวลาถ่ายภาพ
   - ไวต่อ tide, wind setup, waves, wet mud และ local slope
   - ใช้ได้ดีเมื่อ scene ถูก tide-match และผ่าน extraction QA

2. `MANGROVE_EDGE_PROXY`
   - seaward vegetation edge จาก NDVI/vegetation mask
   - ไวต่อ canopy condition, season, turbidity/background และ spatial resolution
   - เป็น ecological/coastal proxy ไม่ใช่ surveyed shoreline

3. `BANK_EDGE` / `SURVEYED_EDGE`
   - มาจาก UAV/field/RTK/validated high-resolution data
   - ใช้เป็น validation หรือ primary geometry ได้ตามคุณภาพข้อมูล

ห้ามผสม indicator คนละประเภทใน regression เดียวโดยไม่ระบุชนิด

---

# Default data sources

## Sentinel-2 L2A — primary

Earth Search:

```text
https://earth-search.aws.element84.com/v1
```

Collection:

```text
sentinel-2-l2a
```

ใช้สำหรับ:

- RGB B04/B03/B02
- NDVI B08/B04
- NDWI B03/B08
- MNDWI B03/B11
- vegetation/water masks
- annual or seasonal shoreline screening

### Resolution rule

- B02/B03/B04/B08 native = 10 m
- B11 native = 20 m
- MNDWI ที่ใช้ B11 ต้องถือว่า analytical support มี effective native resolution 20 m แม้จะ resample ไป 10 m เพื่อ alignment
- อย่าอ้าง MNDWI shoreline ว่าเป็น native 10 m

ค่าเริ่มต้นที่ปลอดภัย: วิเคราะห์ MNDWI บน common 20 m analysis grid และใช้ RGB/NDWI 10 m เป็น supporting QA

## Landsat Collection 2 L2 — historical extension

ใช้เมื่อจำเป็นต้องย้อนก่อน Sentinel-2 หรือเพิ่ม temporal depth

Collection:

```text
landsat-c2-l2
```

ต้องแยก uncertainty เพราะ native resolution แตกต่างจาก Sentinel-2 และห้ามรวม rate โดยไม่บันทึก sensor/source ต่อ epoch

## Sentinel-1 GRD — supplementary only

Collection:

```text
sentinel-1-grd
```

ใช้ช่วยดู flood/wetness/coastal context หรือ gap จาก optical ได้ แต่ห้ามใช้ radar-derived shoreline เป็น primary metric จนกว่าวิธี extraction จะ validate สำหรับพื้นที่นั้น

## Tide

ลำดับ source:

1. official Hydrographic Department / official tide table
2. secondary tide table ที่มี station/source/provenance ชัดเจน
3. model/reanalysis ใช้เป็น supplementary พร้อม flag

ต้องเก็บ:

- station
- station coordinates ถ้ามี
- datum
- source tier
- scene-time tide
- target tide
- tide delta
- interpolation method
- confidence/QA

**ห้าม copy datum offset หรือ target tide จากจังหวัดอื่น**

---

# Required inputs

เดินงานต่อจากข้อมูลที่มี อย่าหยุดเพียงเพราะ input ไม่ครบ

ขั้นต่ำอย่างใดอย่างหนึ่ง:

- AOI GeoJSON/KML/KMZ/Shapefile
- plot polygons
- coastline corridor
- longitude/latitude + buffer

ถ้ามีให้ใช้เพิ่ม:

- planting dates
- coastal structures
- tide station
- UAV orthomosaic
- RTK/GCP/survey
- field shoreline points
- control/reference area
- known reclamation/dredging history

---

# Recommended project config

สร้าง config เดียวเป็น source of truth:

```yaml
analysis_name: samut-songkhram-coastal-change
province: samut-songkhram
analysis_crs: EPSG:32647

aoi: data/aoi/samut_songkhram_aoi.geojson
coast_corridor_buffer_m: 1000

period:
  start: 2017-01-01
  end: 2026-12-31

sentinel2:
  stac_api: https://earth-search.aws.element84.com/v1
  collection: sentinel-2-l2a
  max_scene_cloud_pct: 30
  target_months: []
  use_scl_cloud_mask: true

waterline:
  preferred_index: MNDWI
  analysis_grid_m: 20
  threshold_method: otsu_constrained
  require_ocean_connectivity: true
  threshold_sensitivity_delta: 0.05

mangrove_edge:
  enabled: true
  index: NDVI
  analysis_grid_m: 10
  classification: MANGROVE_EDGE_PROXY

tide:
  station: TBD
  datum: TBD
  target_level_m: auto
  max_delta_m: auto

transects:
  spacing_m: 25
  length_seaward_m: 1000
  length_landward_m: 500
  positive_direction: seaward

outputs: data/derived/coastal-change
```

`target_level_m`, `max_delta_m`, transect spacing และ corridor size ต้องปรับจาก geometry/data quality จริง ไม่ใช่ hardcode ทุกจังหวัดเหมือนกัน

---

# Workflow

## Phase 0 — Preserve existing work

ก่อนแก้ repo:

1. inspect โครงสร้างเดิม
2. reuse AOI/catalog/scripts ที่มีอยู่
3. อย่าทับ output เดิมที่ผ่าน QA
4. output รุ่นใหม่ใช้ path/version ใหม่เมื่อ methodology เปลี่ยน
5. เก็บ manifest ว่า input/algorithm/version ใดสร้างผลชุดไหน

---

## Phase 1 — Resolve AOI and coastal eligibility

1. โหลด AOI/plot polygons
2. repair invalid geometry ถ้าจำเป็น
3. reproject ไป projected CRS ที่เหมาะกับพื้นที่
4. สร้าง coastal analysis corridor
5. classify geometry:
   - `MARINE_SHORELINE_ELIGIBLE`
   - `ESTUARY_EDGE`
   - `BANK_EDGE`
   - `INLAND_NOT_ELIGIBLE`
6. อย่าฝืนคำนวณ marine erosion metric กับแปลงที่อยู่ลึกในคลอง/บนบก

ผลลัพธ์:

```text
aoi.geojson
coastal_corridor.geojson
eligibility.csv
```

---

## Phase 2 — Build reproducible scene catalog

ค้น scene ด้วย geometry จริงและ RFC3339 datetime

ตัวอย่าง:

```python
payload = {
    "collections": ["sentinel-2-l2a"],
    "intersects": geometry,
    "datetime": "2025-01-01T00:00:00Z/2025-12-31T23:59:59Z",
    "limit": 100,
}
```

เก็บอย่างน้อย:

- sensor/provider/collection
- scene_id
- acquisition UTC
- acquisition Asia/Bangkok
- scene cloud %
- AOI valid %
- cloud/shadow % inside coastal corridor
- source assets
- source URL/STAC item
- orbit/tile where relevant
- initial role
- reject reason

อย่าคัด scene จาก scene-level cloud cover อย่างเดียว ต้องตรวจ cloud/shadow ใน AOI จริง

### Cloud / invalid mask

สำหรับ Sentinel-2 ใช้ SCL/cloud mask เพื่อ reject อย่างน้อย:

- cloud shadow
- medium/high probability cloud
- cirrus
- snow/ice ถ้ามี
- nodata/defective pixels

อย่าใช้ SCL `water` class เป็น ground truth ของ shoreline extraction เพราะจะ circular กับงานที่กำลังวิเคราะห์

---

## Phase 3 — Season matching

ก่อนเทียบหลายปี ให้ลด seasonal bias:

1. เลือกเดือน/season ที่มี scene usable มากที่สุดข้ามปี
2. ให้ priority same-season pair
3. ถ้าต้องใช้ต่างฤดู ให้ flag `SEASON_MISMATCH`
4. vegetation-edge analysis ต้องระวัง phenology และ canopy condition
5. waterline analysis ยังต้องผ่าน tide matching แม้ฤดูตรงกัน

Scene ที่สวยกว่าแต่คนละฤดู/น้ำต่างมาก ไม่จำเป็นต้องเป็น scene ที่ดีกว่าสำหรับ change metric

---

## Phase 4 — Tide catalog and scene-time matching

สำหรับทุก candidate WATERLINE scene:

1. หา tide station ที่เหมาะที่สุด
2. ตรวจ datum relation
3. interpolate/predict water level ณ acquisition time
4. บันทึก distance/representativeness ของ station ถ้าทำได้
5. เลือก target tide จาก distribution ของ usable scenes หรือจาก study design
6. คำนวณ `tide_delta = tide_scene - tide_target`
7. rank scenes ตาม:
   - cloud/validity
   - tide delta
   - season
   - spatial coverage
   - temporal representativeness

กำหนด role เช่น:

```text
WATERLINE_PRIMARY
WATERLINE_SUPPORT
VEGETATION_EDGE_ONLY
VISUAL_ONLY
REJECT
```

ถ้า tide ไม่ผ่าน ห้ามฝืนใช้เป็น WATERLINE_PRIMARY

### Important: tide matching is not full tide correction

การเลือกภาพที่ระดับน้ำใกล้กันช่วยลด bias แต่ไม่ได้ normalize waterline ทางแนวนอนทั้งหมด

ถ้ามี local foreshore slope ที่เชื่อถือได้ สามารถใช้ optional horizontal correction:

```text
dx = dh / tan(beta)
```

โดย:

- `dh` = water-level difference
- `beta` = local beach/mudflat slope angle

แต่ห้ามใช้สูตรนี้กับ mudflat ลาดต่ำมากหรือ slope ที่เดา เพราะ error สามารถขยายมหาศาลได้

ถ้าไม่มี reliable slope ให้ **match tide + report residual uncertainty** แทนการสร้าง pseudo-corrected shoreline

---

## Phase 5 — Prepare native analytical raster

### WATERLINE candidate products

อย่างน้อยสร้าง:

```text
NDWI = (Green - NIR) / (Green + NIR)
MNDWI = (Green - SWIR1) / (Green + SWIR1)
```

สำหรับ Sentinel-2:

```text
NDWI  = (B03 - B08) / (B03 + B08)   # native 10 m bands
MNDWI = (B03 - B11) / (B03 + B11)   # limited by B11 native 20 m
```

อย่า resample 20 m B11 เป็น 10 m แล้วตีความว่าได้ข้อมูลใหม่ 10 m

### MANGROVE_EDGE_PROXY

```text
NDVI = (B08 - B04) / (B08 + B04)
```

อาจใช้ additional spectral/context rules เพื่อแยก vegetation ออกจาก turbid water/wet soil แต่ต้องบันทึก method และ validation

---

## Phase 6 — Extract WATERLINE

Default method เป็น **index threshold + ocean connectivity + QA** ไม่ใช่ threshold อย่างเดียว

ขั้นตอน:

1. clip raster to coastal corridor
2. mask cloud/shadow/nodata
3. compute NDWI/MNDWI
4. estimate threshold เช่น Otsu ภายใน valid coastal zone
5. constrain threshold range ถ้า Otsu หลุดจาก physically plausible separation
6. classify water candidate
7. retain ocean/sea-connected component
8. remove isolated ponds/noise ตาม geometry rules
9. derive land-water boundary ด้วย marching contour/vector boundary
10. clip ให้เหลือ shoreline corridor ที่สนใจ
11. preserve raw + cleaned geometry

### Threshold sensitivity QA

อย่าเก็บ shoreline จาก threshold เดียวโดยไม่ทดสอบ

อย่างน้อย re-run:

```text
T - delta
T
T + delta
```

เช่น `delta = 0.05` เป็น starting value ไม่ใช่ค่าตายตัว

คำนวณ positional spread ของ shoreline จาก threshold variants เพื่อเป็นหนึ่งใน uncertainty components

### Mudflat / turbid-water guard

ถ้าพื้นที่เป็น muddy intertidal coast:

- wet mud อาจถูกจัดเป็น water
- turbid water อาจ overlap spectral signature กับ sediment
- low tide อาจทำ waterline เคลื่อนไกลมากโดยไม่ได้หมายถึง erosion/accretion

ต้อง inspect RGB + NDWI + MNDWI + tide พร้อมกัน และลด confidence เมื่อ boundary ไม่ stable

---

## Phase 7 — Extract MANGROVE_EDGE_PROXY

1. compute vegetation mask จาก NDVI/context
2. restrict to plausible mangrove/coastal vegetation zone
3. choose seaward-connected vegetation boundary
4. remove tiny disconnected vegetation patches ตาม scale
5. vectorize edge
6. label ทุก feature ว่า `MANGROVE_EDGE_PROXY`

ห้ามเรียก edge นี้ว่า land edge หรือ sediment edge โดยอัตโนมัติ

ถ้ามี UAV/field validation ให้เก็บ:

- validation date
- source
- positional RMSE/offset ถ้าคำนวณได้
- confusion/edge agreement
- status เช่น `VALIDATED_PROXY`

---

## Phase 8 — Geometric co-registration QA

ก่อนตีความการขยับระดับ 10–30 m ต้องตรวจว่า raster epochs align กันจริง

ใช้ stable features ถ้ามี เช่น:

- road intersections
- large permanent structures
- seawall corners
- bridge piers
- stable inland edges

คำนวณ/ประเมิน epoch-to-reference offset

ถ้า misregistration ใกล้เคียงกับ measured shoreline change:

```text
RESULT = WITHIN_UNCERTAINTY
```

ไม่ควรรายงานเป็น erosion/accretion signal

---

## Phase 9 — Create fixed transects

สร้าง baseline/reference coast หนึ่งชุด แล้วใช้ transect geometry เดิมกับทุก epoch

หลักการ:

- projected CRS in metres
- transects roughly normal to coast
- spacing ตาม scale/curvature เช่น 25–50 m เป็น starting point
- transect ยาวพอครอบคลุมทุก shoreline epoch
- convention เดียวกัน เช่น positive = seaward
- geometry IDs stable across reruns

กรณี shoreline ตัด transect หลายครั้ง:

- resolve ด้วย expected coastal side/ocean connectivity
- เก็บ `MULTIPLE_INTERSECTION` QA
- ห้ามสุ่มเลือก intersection

---

## Phase 10 — Calculate shoreline metrics

ต่อ transect และ indicator type:

### NSM — Net Shoreline Movement

```text
NSM = position_latest - position_earliest
```

positive ตาม convention นี้ = seaward
negative = landward

### EPR — End Point Rate

```text
EPR = NSM / elapsed_years
```

### SCE — Shoreline Change Envelope

```text
SCE = max(position_all_epochs) - min(position_all_epochs)
```

รายงานเป็น magnitude ไม่ใช่ direction

### LRR — Linear Regression Rate

fit:

```text
position = a + b * time
```

`b` = shoreline movement rate m/year

เก็บอย่างน้อย:

- slope
- intercept
- n_epochs
- R²
- standard error / confidence interval ถ้าคำนวณได้

ถ้ามี per-epoch uncertainty ที่เหมาะสม สามารถเพิ่ม Weighted Linear Regression แต่ต้องบันทึก weighting method

### Minimum epoch guard

- 2 epochs: ใช้ NSM/EPR ได้ แต่ trend confidence ต่ำ
- 3+ epochs: เริ่มใช้ regression screening ได้
- หลายปี/หลาย epoch ที่ tide+season ผ่าน QA: confidence สูงขึ้น

ห้ามใช้ 2 จุดแล้วเรียก long-term trend แบบแข็งแรง

---

## Phase 11 — Apparent land gain / loss polygons

การทำ polygon difference ใช้ได้เป็น spatial communication แต่ต้องตั้งชื่อให้ตรง indicator

สำหรับ WATERLINE:

```text
APPARENT_WATERLINE_SEAWARD_ZONE
APPARENT_WATERLINE_LANDWARD_ZONE
```

สำหรับ vegetation edge:

```text
VEGETATION_ADVANCE_ZONE
VEGETATION_RETREAT_ZONE
```

อย่าใช้ชื่อ `NEW_LAND` หรือ `SEDIMENT_GAIN` โดยอัตโนมัติ

คำนวณ area เฉพาะเมื่อ:

- pair มี compatible indicator
- CRS เป็น projected area-appropriate CRS
- scene QA ผ่าน
- tide/season role รองรับ
- geometry topology valid

รายงาน area พร้อม uncertainty/interpretation guard

---

## Phase 12 — Uncertainty budget

อย่าใช้ pixel size อย่างเดียวเป็น uncertainty

เก็บอย่างน้อย:

1. `U_grid` — analytical grid / effective source resolution
2. `U_coreg` — co-registration error
3. `U_threshold` — threshold sensitivity spread
4. `U_tide` — residual tide-related positional uncertainty ถ้าประเมินได้
5. `U_digitize_or_vectorize` — extraction/vector cleaning sensitivity ถ้ามี
6. `U_validation` — UAV/field positional uncertainty ถ้ามี

ถ้าสมมติ independence ได้และมีเหตุผล สามารถคำนวณ combined RSS:

```text
U_total = sqrt(U_grid² + U_coreg² + U_threshold² + U_tide² + ...)
```

ถ้าสมมติ independence ไม่ได้ ให้รายงาน component แยกและใช้ conservative screening threshold แทน

### Classification

ใช้ uncertainty-driven classification เช่น:

```text
APPARENT_SEAWARD      if change > +U_screen
WITHIN_UNCERTAINTY    if abs(change) <= U_screen
APPARENT_LANDWARD     if change < -U_screen
```

อย่า hardcode ±20 m ทุกงาน

ถ้า analysis จริงอยู่บน 20 m grid และองค์ประกอบอื่นยังประเมินไม่ได้ ±20 m อาจใช้เป็น conservative starting screening band ได้ แต่ต้องบันทึกว่าเป็น heuristic

---

## Phase 13 — Multi-indicator evidence synthesis

สรุป WATERLINE กับ MANGROVE_EDGE_PROXY แยกก่อน แล้วจึงเทียบกัน

ตัวอย่าง evidence pattern:

### Stronger apparent accretion signal

- tide-matched WATERLINE ขยับ seaward หลาย epoch
- vegetation edge ขยับ seaward ในทิศทางสอดคล้อง
- change เกิน uncertainty
- ไม่มี obvious reclamation/structure confounder
- UAV/field พบ stable exposed substrate/vegetation establishment

ยังเรียก `APPARENT_ACCRETION` จนกว่าจะมี elevation/sediment confirmation

### Possible erosion signal

- tide-matched WATERLINE landward หลาย epoch
- vegetation edge retreat สอดคล้อง
- change เกิน uncertainty
- field/UAV พบ bank scarp/root exposure หรือ loss pattern

### Ambiguous

- waterline และ vegetation edge คนละทิศ
- tide mismatch สูง
- cloud/turbidity/wet mud สูง
- change ใกล้ uncertainty
- coastal engineering/dredging/reclamation เปลี่ยนระหว่าง epoch

สถานะต้องเป็น `AMBIGUOUS` หรือ `INSUFFICIENT_EVIDENCE` ไม่ฝืนสรุป

---

## Phase 14 — Planting-aware analysis

ถ้ามีโครงการปลูกป่าชายเลน ให้ผูกทุก scene กับ planting timeline จริง

เก็บ:

```text
BEFORE_PLANTING_VERIFIED
BEFORE_COMPLETION_START_UNKNOWN
DURING_IMPLEMENTATION
CONFIRMED_POST_COMPLETION
```

ถ้ามีแค่วันปลูกเสร็จ อย่าเดาวันเริ่มปลูก

ขั้นต่ำต่อ plot:

- last usable observation before completion
- first usable confirmed post-completion observation
- latest observation
- days since completion
- waterline NSM/EPR
- vegetation-edge NSM/EPR
- uncertainty class
- evidence status

ห้ามสรุปว่า planting caused erosion reduction เพียงเพราะ post-planting shoreline ดีขึ้น

---

## Phase 15 — Controls and confounders

ก่อนอ้าง causal effect ต้องตรวจ candidate control/reference area สำหรับ:

- seawall / revetment / geotube / bamboo fence
- dredging
- reclamation/fill
- navigation channel maintenance
- river-mouth migration
- aquaculture/land-use change
- other mangrove planting
- storm/cyclone damage
- different geomorphology

สถานะ control:

```text
CANDIDATE_UNVERIFIED
VERIFIED_COMPARABLE
REJECTED_CONFOUNDED
```

ห้ามใช้ treatment-control difference เป็น causal effect จน control ผ่าน verification

---

## Phase 16 — UAV / field validation

UAV/field ใช้ยกระดับ evidence ไม่ใช่เพื่อทำให้ satellite metric ดูละเอียดขึ้น

ตรวจได้ เช่น:

- actual bank edge
- vegetation edge
- exposed mudflat/sediment surface
- erosion scarp
- root exposure
- coastal structures
- ground control positions

### One-epoch UAV rule

ถ้ามี UAV เพียง 1 epoch:

```text
HIGH_RESOLUTION_BASELINE
```

ใช้ validate geometry/context ได้ แต่ห้ามคำนวณ UAV-derived erosion/accretion rate

repeat UAV ที่มี georeference/same-datum ดีจึงใช้ high-resolution change measurement ได้

---

# Evidence Readiness Gate

ก่อนสรุปผล ให้สร้าง `evidence_readiness.json`

## Gate A — AOI / CRS

PASS เมื่อ:

- geometry ถูกต้อง
- analysis CRS เป็น metre-based/projected
- coastal eligibility ชัด

## Gate B — Scene QA

PASS เมื่อ:

- source scene traceable
- AOI valid pixels เพียงพอ
- cloud/shadow ไม่บัง coast สำคัญ
- season role ชัด

## Gate C — Tide QA

PASS สำหรับ WATERLINE เมื่อ:

- station/source/datum ชัดพอ
- scene-time tide มี provenance
- tide delta ผ่าน tolerance ของ study

ถ้าไม่ผ่าน ให้ลด role เป็น supporting/visual

## Gate D — Extraction QA

PASS เมื่อ:

- threshold/vectorization reproducible
- ocean connectivity ถูกใช้ตามความเหมาะสม
- threshold sensitivity ไม่ทำ geometry กระโดดผิดปกติ
- wet mud/turbidity issue ถูกตรวจ

## Gate E — Geometric / uncertainty QA

PASS เมื่อ:

- co-registration ถูกตรวจ
- uncertainty components ถูกบันทึก
- claimed change เกิน screening uncertainty เมื่อจะเรียก directional signal

## Gate F — Multi-epoch evidence

PASS เมื่อมี epoch เพียงพอกับ metric ที่รายงาน

## Gate G — Validation / causal evidence

ใช้เฉพาะเมื่อจะยกระดับจาก screening ไป claim ที่แรงขึ้น

ต้องมี UAV/field/control/other independent evidence ตาม claim

---

# Claim levels

## Level 0 — Visual context only

ใช้เมื่อ scene/tide/QA ไม่พอ

พูดได้:

> ภาพแสดงสภาพชายฝั่งในช่วงเวลานั้น แต่ยังไม่เหมาะสำหรับใช้วัดการเปลี่ยนแปลงแนวชายฝั่งเชิงปริมาณ

## Level 1 — Satellite screening

พูดได้:

> แนว waterline ที่คัดระดับน้ำใกล้เคียงกันแสดง apparent landward/seaward movement ในบางช่วง โดยผลยังอยู่ในระดับ satellite screening และมี uncertainty จาก resolution, tide และ boundary extraction

## Level 2 — Multi-indicator supported

พูดได้เมื่อ WATERLINE + vegetation/UAV/field สอดคล้อง:

> หลักฐานหลายชนิดสนับสนุนว่าบริเวณนี้มีแนวโน้มการรุกออกทะเล/ถอยเข้าฝั่งในช่วงข้อมูลที่วิเคราะห์ได้

ยังไม่ใช่ causal claim

## Level 3 — Confirmed geomorphic change

ต้องมี survey/elevation/repeat validated high-resolution evidence ที่เพียงพอ

จึงอาจใช้คำว่า confirmed erosion/accretion ตาม method จริง

## Level 4 — Causal project effect

ต้องมี design และ evidence รองรับ causal attribution เช่น verified control, confounder review, adequate pre/post period และ independent validation

ห้ามข้ามจาก Level 1 ไป Level 4

---

# Output contract

อย่างน้อยสร้าง:

```text
data/derived/coastal-change/
  analysis_manifest.json
  scene_catalog.csv
  tide_at_scene.csv
  scene_selection.csv
  shoreline_waterline.geojson
  shoreline_mangrove_edge_proxy.geojson
  transects.geojson
  intersections.csv
  metrics_by_transect.csv
  metrics_by_plot.csv
  pairwise_change_zones.geojson
  uncertainty.csv
  evidence_readiness.json
  summary.json
  qa/
    extraction_qa.json
    coregistration_qa.json
    rejected_scenes.csv
```

`analysis_manifest.json` ต้องเก็บอย่างน้อย:

```json
{
  "method_version": "coastal-erosion-accretion-v1",
  "quantitative_super_resolution_used": false,
  "positive_direction": "seaward",
  "waterline_indicator": "MNDWI/NDWI + ocean connectivity",
  "mangrove_edge_indicator": "MANGROVE_EDGE_PROXY",
  "analysis_crs": "EPSG:32647",
  "source_sensors": ["Sentinel-2"],
  "tide_aware": true
}
```

ถ้า `quantitative_super_resolution_used` เป็น `true` ให้ validation fail

---

# Suggested implementation stack

Python:

```text
pystac-client
rasterio
geopandas
shapely
pyproj
numpy
pandas
scipy
scikit-image
```

ถ้าใช้ Microsoft Planetary Computer ให้ใช้ signed asset URL ตาม package/API ที่ใช้อยู่

แยก code เป็น module เช่น:

```text
scripts/coastal_change/
  catalog_scenes.py
  build_tide_catalog.py
  select_scenes.py
  build_indices.py
  extract_waterline.py
  extract_mangrove_edge.py
  check_coregistration.py
  build_transects.py
  intersect_shorelines.py
  calculate_metrics.py
  build_change_zones.py
  calculate_uncertainty.py
  evidence_gate.py
  build_summary.py
```

---

# Validation checks

ก่อนถือว่างานเสร็จ ต้องตรวจอย่างน้อย:

```text
[ ] AOI อยู่ตำแหน่งจริง
[ ] CRS เป็น projected/metres สำหรับ distance metrics
[ ] Scene IDs และ acquisition times traceable
[ ] Coastal AOI cloud/shadow QA ผ่าน
[ ] Tide source/station/datum ถูกจังหวัด
[ ] WATERLINE scenes ผ่าน tide tolerance
[ ] Analytical resolution ตรงกับ native band support
[ ] ไม่มี SR output ถูกใช้ทำ metric
[ ] WATERLINE raw/cleaned QA ดูสมเหตุสมผล
[ ] MANGROVE_EDGE ถูก label เป็น proxy
[ ] Stable-feature co-registration ถูกตรวจ
[ ] Transects ใช้ geometry เดิมทุก epoch
[ ] Multiple intersections ถูก flag/resolve
[ ] NSM/EPR/LRR/SCE sign convention ถูกต้อง
[ ] Change classification ใช้ uncertainty ไม่ใช่ดูจากสีบนแผนที่
[ ] Area change ใช้ชื่อ apparent/proxy ให้ถูกประเภท
[ ] Planting dates ไม่ถูกเดา
[ ] Control ยังไม่ถูกเรียก verified ถ้ายังไม่ได้ตรวจ
[ ] Summary ไม่อ้าง causal impact เกิน evidence gate
[ ] analysis_manifest.json ระบุ quantitative_super_resolution_used=false
```

---

# Failure modes and recovery

## WATERLINE กระโดดผิดปกติ

ตรวจ:

1. tide mismatch
2. wet mud/turbidity
3. cloud shadow
4. threshold instability
5. wrong ocean connected component
6. raster co-registration
7. river mouth/channel migration

อย่าแก้ด้วยการ smooth geometry หนัก ๆ จน signal หาย

## ปีหนึ่งไม่มี scene ที่ tide ผ่าน

- อย่าฝืนเลือก
- mark year `NO_WATERLINE_SCENE_PASS`
- ยังใช้ `VISUAL_ONLY` หรือ `MANGROVE_EDGE_PROXY` ได้ถ้า QA รองรับ
- regression ต้องรับ missing epoch ได้

## Sentinel-2 กับ Landsat ให้ผลต่างกัน

- แยก sensor QA
- inspect effective resolution
- อย่า resample แล้วถือว่าเท่ากัน
- ใช้ overlap years ทำ cross-sensor comparison ก่อนรวม time series

## Waterline กับ vegetation edge คนละทิศ

สถานะ default = `AMBIGUOUS`

สาเหตุอาจเป็น:

- intertidal width/tide
- mangrove colonization บน mudflat
- vegetation loss โดย shoreline ยังไม่เปลี่ยน
- threshold/registration issue

ต้อง inspect เพิ่ม ไม่เลือก indicator ที่เข้ากับ narrative ที่ต้องการ

---

# Default execution behavior for Codex/agent

เมื่อผู้ใช้สั่ง เช่น:

> วิเคราะห์กัดเซาะ/ดินงอกพื้นที่นี้ย้อนหลัง 3 ปี

ให้ทำต่อเนื่องดังนี้โดยไม่ถามซ้ำถ้าข้อมูลหาได้จาก repo/public source:

1. inspect repo/AOI เดิม
2. สร้างหรือ reuse config
3. catalog scenes
4. build tide catalog
5. select same-season/tide-aware scenes
6. extract native-resolution WATERLINE
7. extract MANGROVE_EDGE_PROXY ถ้ามีประโยชน์
8. coregistration QA
9. build fixed transects
10. calculate NSM/EPR/LRR/SCE
11. calculate uncertainty and classification
12. build apparent change zones
13. run evidence gate
14. generate machine-readable summary
15. ถ้ามีเว็บอยู่แล้ว ให้เพิ่ม derived data แบบ additive โดยไม่ทับของเดิม
16. run tests/validation

หากติด source จริง ให้รายงาน blocker แบบเจาะจงพร้อมทำส่วนที่ทำได้ต่อ ไม่หยุดทั้ง workflow

---

# Relationship to other skills

## `skills/sentinel-2-super-resolution/SKILL.md`

ใช้เฉพาะเมื่อผู้ใช้ต้องการภาพ Sentinel-2 ที่ดูคมขึ้นสำหรับการแสดงผล

ลำดับที่ถูกต้องเมื่อใช้ทั้งสอง skill คือ:

```text
native satellite data
        ↓
coastal-erosion-accretion quantitative analysis
        ↓
metrics / shoreline / uncertainty / evidence gate

native satellite data
        ↓
sentinel-2-super-resolution
        ↓
visual-only enhanced layer
```

สอง branch นี้ต้องไม่ย้อนมาปะปนกัน

---

# Final rule

เป้าหมายของ skill นี้ไม่ใช่ทำแผนที่ที่ดูเหมือนมีการกัดเซาะหรือดินงอก แต่คือสร้าง **หลักฐาน shoreline change ที่ reproducible, tide-aware, uncertainty-aware และ audit ได้**

ถ้าหลักฐานบอกว่า change ยังเล็กกว่าความไม่แน่นอน ผลที่ถูกต้องคือ `WITHIN_UNCERTAINTY` ไม่ใช่การฝืนสรุป erosion/accretion
