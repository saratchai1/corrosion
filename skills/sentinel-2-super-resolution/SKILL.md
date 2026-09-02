---
name: sentinel-2-super-resolution
description: Reusable workflow for creating visually sharper Sentinel-2 L2A RGB/NIR imagery with 4x super-resolution, validating the output, and publishing non-destructive web comparisons. Based on the tested Samut Songkhram workflow in saratchai1/corrosion.
---

# Sentinel-2 Super-Resolution Skill

## Purpose

ใช้ skill นี้เมื่อผู้ใช้ต้องการเพิ่มรายละเอียดเชิงภาพของ Sentinel-2 โดยเฉพาะงานลักษณะ:

- ทำ Sentinel-2 10 m ให้ดูละเอียดขึ้นบนกริด 2.5 m
- ทำ before/after หรือ swipe comparison บนเว็บ
- ขยายรายละเอียดแนวป่าชายเลน ร่องน้ำ ขอบพื้นที่ หรือ texture ของภูมิประเทศ
- ทำเวอร์ชันทดลองแยกจากเว็บเดิมโดยไม่ทับ production
- ประมวลผลหลาย AOI / หลายแปลงแบบ batch
- สร้าง web-ready imagery จาก Sentinel-2 โดยไม่ใช้ image generator

ค่าเริ่มต้นของ skill นี้คือ **LDSR-S2 / OpenSR ผ่าน `geoai-py[sr]`** สำหรับ 4 แบนด์ 10 m: Red, Green, Blue, NIR.

ผล 4x คือรายละเอียดที่โมเดล reconstruct บนกริดละเอียดขึ้น ไม่ใช่การเปลี่ยน native sensor resolution ของ Sentinel-2 ดังนั้นต้องแยกการใช้งานเชิงภาพออกจากการอ้างเชิงปริมาณเสมอ

---

# Golden rules

## 1. ห้ามใช้ image generator

งานนี้ต้องประมวลผลจาก Sentinel-2 raster จริงเท่านั้น

- ใช้ STAC / COG / GeoTIFF จริง
- ใช้ model inference จริง
- ห้ามสร้างภาพเลียนแบบดาวเทียมด้วย generative image tool
- ห้ามแทน output inference ด้วยภาพตกแต่ง

## 2. ห้ามทับของเดิมโดยอัตโนมัติ

ถ้ามีเว็บหรือ dataset เดิมอยู่แล้ว:

- สร้าง branch ใหม่ เช่น `feature/<area>-sentinel-superres-v1`
- สร้าง path แยก เช่น `web/public/data/superres25/`
- สร้าง preview deployment ก่อน
- อย่าเปลี่ยน production default จนกว่าผู้ใช้จะสั่ง

## 3. ห้าม hardcode Sentinel tile จาก AOI อื่น

ต้องค้นหา scene ที่ **geometry ครอบ AOI จริง** ทุกครั้ง

กรณีที่เคยเกิดขึ้นจริง:

- แปลง 91–98 STC ใช้ tile `47PPQ`
- 87-VSD อยู่คนละ footprint และต้องใช้ `47PNQ`

ดังนั้นห้ามสมมติว่าแปลงในจังหวัดเดียวกันอยู่ tile เดียวกัน

ก่อน inference ต้องตรวจ:

- item geometry intersects AOI
- จุดกึ่งกลาง AOI อยู่ใน item footprint
- อ่าน raster แล้วมี valid data สูงพอ
- `native_rgb_nonzero_fraction` ไม่ใกล้ศูนย์

## 4. ห้าม apply Sentinel-2 reflectance offset ซ้ำ

สำหรับ Element 84 Earth Search Sentinel-2 L2A COG ที่ใช้อยู่ใน workflow นี้ ค่าพิกเซลถูกเก็บใน BOA convention ประมาณ `0..10000` อยู่แล้ว

อย่า apply STAC raster scale/offset ซ้ำโดยไม่ตรวจ encoding จริง เพราะเคยทำให้ coastal RGB ถูก clip และภาพมืดผิดปกติ

หลักปฏิบัติ:

```python
raw = src.read(1).astype(np.float32)
data = np.clip(np.rint(raw), 0, 10000).astype(np.uint16)
```

ก่อนใช้วิธีอื่น ให้ inspect sample statistics ของ source raster ก่อน

## 5. ใช้ stretch เดียวกันสำหรับ native และ SR

ถ้าจะเทียบความคม ต้องไม่ทำให้ฝั่ง SR ดูดีกว่าเพราะ contrast คนละแบบ

- หา RGB stretch limits จาก native image
- ใช้ limits ชุดเดียวกันกับ native และ SR
- ใช้ gamma เดียวกัน
- web comparison ต้องใช้ extent และ crop เดียวกัน

## 6. อย่าเรียก output ว่า native 2.5 m

ถ้าต้องบันทึก metadata ให้ใช้คำเช่น:

- `4x super-resolution output`
- `2.5 m output grid`
- `model-reconstructed detail`

ถ้าผู้ใช้ต้องการเว็บ visual-only และไม่ต้องการข้อความเคลม ให้หน้าเว็บแสดงเฉพาะภาพ, plot/date, swipe และ zoom โดยไม่ต้องเขียนคำอธิบาย resolution บน UI

---

# Default data source

## Sentinel-2

ใช้ Earth Search:

```text
https://earth-search.aws.element84.com/v1
```

Collection:

```text
sentinel-2-l2a
```

แบนด์หลักสำหรับ LDSR-S2:

| Model order | Sentinel-2 | Earth Search asset | Native resolution |
|---|---|---|---|
| 1 | B04 Red | `red` | 10 m |
| 2 | B03 Green | `green` | 10 m |
| 3 | B02 Blue | `blue` | 10 m |
| 4 | B08 NIR | `nir` | 10 m |

ห้ามสลับลำดับเป็น B,G,R,NIR ตอนเขียน input stack

---

# Required inputs

รับข้อมูลเท่าที่มีและเดินงานต่อได้ อย่าหยุดเพียงเพราะ input ไม่ครบ

ขั้นต่ำอย่างใดอย่างหนึ่ง:

1. AOI Polygon — GeoJSON/KML/KMZ/Shapefile
2. จุด longitude/latitude
3. plot polygons ใน project repo

ข้อมูลเสริมที่ควรใช้:

- target date หรือ date range
- cloud threshold
- plot IDs
- output branch
- web project/path
- preferred acquisition season
- tide constraint ถ้าเป็นงานชายฝั่ง

---

# Recommended configuration

สร้าง config เดียวเป็น source of truth เช่น:

```yaml
name: samut-songkhram-superres
collection: sentinel-2-l2a
stac_api: https://earth-search.aws.element84.com/v1
start_date: 2025-01-01
end_date: 2025-01-31
max_cloud_cover: 10
bands:
  - red
  - green
  - blue
  - nir
scale: 4
sampling_steps: 25
patch_size: 128
overlap: 16
scale_factor: 10000
output_grid_m: 2.5
compute_uncertainty: false
web_output: web/public/data/superres25
```

สำหรับงานหลายแปลง ให้แต่ละแปลงมี:

```yaml
plots:
  - id: 91-stc
    label: 91-STC
    geometry: data/aoi/plot_91.geojson
  - id: 92-stc
    label: 92-STC
    geometry: data/aoi/plot_92.geojson
```

อย่ากำหนด Sentinel tile ใน config เว้นแต่ตรวจ footprint แล้ว

---

# Workflow

## Phase 1 — Resolve AOI

1. โหลด AOI geometry
2. ถ้าเป็น plot polygon ให้คำนวณ bbox และ representative center
3. ถ้า AOI เล็กมาก ให้ขยาย context window รอบแปลง
4. เก็บ geometry เดิมไว้สำหรับ metadata

สำหรับ visual comparison ค่าเริ่มต้นที่ใช้งานได้ดีคือ patch 128 × 128 native pixels:

```text
128 × 10 m = 1.28 km ต่อด้าน
```

หลัง 4x SR จะเป็น:

```text
512 × 512 pixels
```

โดย coverage ภาคพื้นดินเท่าเดิม

## Phase 2 — Discover a valid Sentinel-2 scene

อย่าเลือก scene จากชื่อ tile ก่อน

ค้น STAC ด้วย AOI geometry และช่วงเวลา:

```python
payload = {
    "collections": ["sentinel-2-l2a"],
    "intersects": geometry,
    "datetime": "2025-01-01T00:00:00Z/2025-01-31T23:59:59Z",
    "limit": 100,
}
```

จัดอันดับ candidate โดยอย่างน้อย:

1. geometry coverage ของ AOI
2. cloud cover ต่ำ
3. acquisition date ใกล้ target date
4. valid pixel fraction ของ RGB/NIR

ถ้าเป็นหลายแปลง อย่าบังคับทุกแปลงให้ใช้ item ID เดียวกัน ถ้า footprint ไม่ครอบ

## Phase 3 — Read native RGB/NIR patch

ใช้ `rasterio` และ CRS ของ COG จริง

ตัวอย่าง:

```python
from pyproj import Transformer
from rasterio.windows import Window

with rasterio.open(href) as src:
    transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
    x, y = transformer.transform(lon, lat)
    row, col = src.index(x, y)
    half = patch_size // 2
    window = Window(col - half, row - half, patch_size, patch_size)
    raw = src.read(1, window=window, boundless=True, fill_value=0)
```

อ่านทั้ง 4 แบนด์ด้วย window เดียวกันและ stack เป็น:

```text
[R, G, B, NIR]
```

ตรวจทันที:

```python
nonzero_fraction = np.count_nonzero(stack[:3]) / stack[:3].size
```

ถ้าค่าต่ำผิดปกติ อย่า inference ต่อ ให้ค้น scene/tile ใหม่

## Phase 4 — Write inference GeoTIFF

เขียน 4-band UInt16 GeoTIFF ชั่วคราว:

```python
with rasterio.open(
    path,
    "w",
    driver="GTiff",
    width=stack.shape[2],
    height=stack.shape[1],
    count=4,
    dtype="uint16",
    crs=crs,
    transform=transform,
    tiled=True,
    compress="deflate",
) as dst:
    dst.write(stack)
```

อย่า commit intermediate TIFF ถ้าไม่จำเป็น

## Phase 5 — Run LDSR-S2

Dependencies:

```bash
pip install -U "geoai-py[sr]" rasterio pyproj pillow numpy requests
```

Default inference:

```python
import geoai

geoai.super_resolution(
    input_lr_path=str(native_tif),
    output_sr_path=str(sr_tif),
    rgb_nir_bands=[1, 2, 3, 4],
    sampling_steps=25,
    scale=4,
    compute_uncertainty=False,
    scale_factor=10000.0,
    patch_size=128,
    overlap=16,
)
```

ค่าเริ่มต้นที่ผ่านการทดลองแล้ว:

```text
scale = 4
sampling_steps = 25
patch_size = 128
overlap = 16
scale_factor = 10000
```

ถ้าต้องการ uncertainty map ให้เปิด:

```python
compute_uncertainty=True
```

แต่ต้องยืนยัน output contract ของ package version ที่ใช้อยู่ก่อน publish

## Phase 6 — Display normalization

หา stretch limits จาก native RGB เท่านั้น เช่น percentile 1–99:

```python
limits = []
for band in native[:3].astype(np.float32):
    valid = band[np.isfinite(band) & (band > 0)]
    lo, hi = np.percentile(valid, [1, 99])
    limits.append((float(lo), float(hi)))
```

ใช้ limits เดียวกันกับ SR

ถ้า SR output อยู่ช่วง `0..1` ให้ scale กลับก่อน display:

```python
if np.nanmax(data) <= 2.0:
    data = data * 10000.0
```

จากนั้น clip เป็น 0..1 และแปลง WebP/PNG

## Phase 7 — Save web assets

แนะนำ naming:

```text
<plot-id>-10m.webp
<plot-id>-2p5m.webp
```

ชื่อไฟล์ใช้เพื่อ internal organization ได้ แม้หน้าเว็บจะไม่ต้องแสดงข้อความ 10 m / 2.5 m

Web assets ควรเป็น extent เดียวกันและขนาด pixel เท่ากันสำหรับ swipe เช่น:

```text
512 × 512 WebP
```

ฝั่ง native ให้ resize เพื่อการแสดงผลเท่านั้น อย่าเปลี่ยน metadata ว่า native resolution เปลี่ยนตาม

## Phase 8 — Write summary metadata

สร้าง `summary.json` เช่น:

```json
{
  "locations": [
    {
      "id": "91-stc",
      "label": "91-STC",
      "lon": 99.9622,
      "lat": 13.3082,
      "scene_id": "S2A_47PPQ_20250115_0_L2A",
      "date": "2025-01-15",
      "original": "data/superres25/91-stc-10m.webp",
      "superres": "data/superres25/91-stc-2p5m.webp",
      "stats": {
        "native_rgb_nonzero_fraction": 1.0
      }
    }
  ]
}
```

Metadata ขั้นต่ำต่อ output:

- AOI/plot ID
- center / bbox
- Sentinel-2 item ID
- acquisition date
- MGRS/tile ถ้ามี
- source collection
- model/tool name
- scale
- sampling steps
- scale factor
- input band order
- output paths
- valid/nonzero pixel fraction
- model/package version ถ้าดึงได้

---

# Batch processing

ถ้ามีหลายแปลง อย่ารัน sequential ถ้า runtime แพง

ใช้ GitHub Actions matrix เช่น:

```yaml
strategy:
  fail-fast: false
  max-parallel: 4
  matrix:
    plot:
      - 91-STC
      - 92-STC
      - 93-STC
      - 94-STC
```

แต่ละ job:

1. checkout
2. install dependencies
3. resolve scene สำหรับ plot นั้น
4. run SR
5. validate
6. upload artifact

หลังทุก job ผ่าน ให้มี `publish` job รวม artifacts เป็น dataset เดียว

อย่าให้ matrix jobs push เข้า branch พร้อมกัน เพราะเสี่ยง non-fast-forward conflict

หลักที่ควรใช้:

```text
matrix jobs -> artifacts only
one publish job -> one commit/push
```

---

# Validation

## Visual publish validation

ขั้นต่ำต้องผ่านทั้งหมด:

1. native image exists
2. SR image exists
3. output dimensions ถูกต้อง
4. file size ไม่ผิดปกติจนเกือบว่าง
5. image ไม่ flat / ไม่ดำทั้งภาพ
6. native valid fraction สูงพอ
7. output extent ตรงกับ native
8. หน้าเว็บโหลดทั้งสองฝั่งได้

ตัวอย่าง:

```python
from PIL import Image, ImageStat

image = Image.open(path).convert("RGB")
assert image.size == (512, 512)
extrema = ImageStat.Stat(image).extrema
assert any(high - low > 10 for low, high in extrema)
```

สำหรับ patch ที่ควรมีข้อมูลเต็ม:

```python
assert native_rgb_nonzero_fraction > 0.9
```

ถ้า AOI อยู่ริม tile หรือทะเลล้วน อาจต้องปรับเกณฑ์ตามบริบท แต่อย่าปล่อยภาพดำผ่าน validation

## Spectral consistency check

ถ้าจะใช้ SR มากกว่าแค่ดูภาพ ให้ทำ downsample-back check:

1. downsample SR กลับสู่ native grid
2. เทียบกับ original Sentinel-2
3. บันทึก MAE / bias / correlation ต่อแบนด์
4. inspect spatial residual

อย่าตั้ง universal threshold โดยไม่มี benchmark ของงานนั้น

## High-resolution truth validation

ถ้าจะใช้รายละเอียด SR เพื่อวัดวัตถุหรือขอบเขตเล็ก:

- เทียบ drone orthomosaic
- commercial high-resolution imagery ที่มีสิทธิ์ใช้
- field/GNSS truth

ถ้ายังไม่มี truth ให้ใช้ SR เป็น visual aid / screening เท่านั้น

---

# Analytical guardrails

## RGB / visual inspection

ใช้ SR ได้ดีสำหรับ:

- ดู morphology คร่าว ๆ
- ดู texture และ edge ที่ native image อ่านยาก
- ช่วยเลือก ROI
- ช่วย review แนวป่าชายเลน/ร่องน้ำ
- presentation / visual comparison

## NDVI

LDSR-S2 มี NIR และ Red จึงคำนวณ index บน SR grid ได้ในเชิงทดลอง แต่ห้ามตีความว่าทุก pixel 2.5 m เป็น observation จริง

ควรเทียบผล downsample-back กับ native NDVI ก่อนใช้เชิงปริมาณ

## NBR / dNBR / SWIR analysis

NBR ต้องใช้ NIR + SWIR2 และ Sentinel-2 B12 เป็น native 20 m

LDSR-S2 RGB+NIR 4-band workflow นี้ **ไม่ได้ super-resolve B12**

ดังนั้นห้ามทำสิ่งต่อไปนี้แล้วเรียกว่า dNBR 2.5 m จริง:

- resize B12 20 m เป็น 2.5 m ด้วย bicubic อย่างเดียว
- combine LDSR NIR 2.5 m กับ interpolated B12 แล้วเคลม spatial detail 2.5 m

ถ้างานต้องการ SWIR ให้:

1. ใช้ model/workflow ที่รองรับ 20 m bands เช่น SEN2SR/OpenSR workflow ที่ตรวจสอบ version แล้ว หรือ
2. ทำ index ที่ native / harmonized resolution และใช้ SR เฉพาะ RGB/NIR visual layer

## Shoreline / coastal erosion

SR อาจช่วยให้มอง water/vegetation edge ง่ายขึ้น แต่ห้ามสรุปว่า shoreline movement มี precision 2.5 m เพียงเพราะ output grid เป็น 2.5 m

สำหรับ quantitative shoreline change ต้องพิจารณาอย่างน้อย:

- native sensor resolution
- geolocation error
- tide/water level
- cloud/shadow
- edge extraction uncertainty
- high-resolution benchmark

---

# Web publishing pattern

ถ้าผู้ใช้ต้องการ “แค่ดูว่าคมขึ้นไหม” ให้ทำ UI เรียบง่าย:

- plot selector
- image swipe divider
- zoom
- reset
- acquisition date

ไม่ต้องใส่บทความหรือ claim panel ถ้าผู้ใช้ไม่ได้ขอ

โครง:

```html
<div class="frame" id="frame">
  <div class="plane" id="plane">
    <img id="baseImage" />
    <div class="clip" id="clip">
      <img id="detailImage" />
    </div>
  </div>
  <div class="divider" id="divider"></div>
</div>
```

โหลดรายการแปลงจาก `summary.json` แทน hardcode ชื่อไฟล์ใน HTML

---

# Git / deploy rules

## Branch

ใช้ branch แยก เช่น:

```text
feature/samut-songkhram-superres-2p5-web-v1
```

## Generated binary assets

WebP ขนาดเล็ก commit ได้ตามความเหมาะสม

อย่า commit:

- model checkpoint 1+ GB
- raw Sentinel tile ใหญ่
- temporary native/SR GeoTIFF หลาย GB
- pip/model cache

## Push conflict

ถ้า publish job เจอ:

```text
rejected (fetch first)
non-fast-forward
```

อย่ารัน inference ใหม่ทันที

ให้แก้ publish flow โดย:

1. fetch latest remote branch
2. rebase/cherry-pick generated commit หรือ
3. checkout latest branch ก่อน assemble/commit
4. push จาก publish job เดียว

## Deploy

ก่อนบอกผู้ใช้ว่า publish เสร็จ ต้องตรวจว่า deployment status เป็น `READY`

ถ้าเป็น preview protected deployment ให้สร้าง share URL เมื่อจำเป็น

---

# Failure modes and fixes

## Output ดำทั้งภาพ

ตรวจตามลำดับ:

1. scene footprint ครอบ AOI หรือไม่
2. nonzero fraction
3. raster window อยู่นอก bounds หรือไม่
4. apply offset/scale ซ้ำหรือไม่
5. input band order ถูกหรือไม่
6. display stretch ใช้ค่าผิด range หรือไม่

## Output คมแต่สีเพี้ยน

- ตรวจ input band order `[R,G,B,NIR]`
- ตรวจ scale factor
- ใช้ stretch จาก native เดียวกัน
- อย่า auto-enhance SR แยกจาก native

## แปลงหนึ่งดำ แต่แปลงอื่นดี

สันนิษฐานแรกคือ tile/footprint mismatch ไม่ใช่ model failure

ให้ search scene สำหรับแปลงนั้นแยกต่างหาก

## GitHub Actions ช้าเพราะ dependency

`geoai-py[sr]` และ PyTorch dependency ใหญ่มาก

แนวทาง:

- ใช้ pip cache
- ใช้ matrix parallel
- reuse model cache ถ้า runner environment รองรับ
- อย่ารันทุกแปลงใหม่เมื่อแก้แค่ HTML/CSS
- แยก imagery workflow ออกจาก web UI workflow

## Web เปลี่ยนแต่ inference เริ่มใหม่โดยไม่จำเป็น

กำหนด workflow `paths:` ให้ละเอียด

เช่น imagery workflow trigger เฉพาะ:

```text
scripts/superres/**
config/superres/**
.github/workflows/superres.yml
```

ไม่ควร trigger เมื่อแก้ CSS/JS อย่างเดียว

---

# Recommended repository structure

```text
skills/
  sentinel-2-super-resolution/
    SKILL.md

config/
  superres/
    <area>.yml

scripts/
  superres/
    discover_scene.py
    build_plot.py
    validate.py
    assemble_web_dataset.py

outputs/
  superres/
    <area>/
      <plot>/
        native_rgbnir.tif
        superres_rgbnir.tif

web/
  public/
    data/
      superres25/
        summary.json
        91-stc-10m.webp
        91-stc-2p5m.webp
```

Intermediate `outputs/` ควรอยู่ใน `.gitignore` เว้นแต่เป็น lightweight QA file

---

# Definition of done

งานถือว่าเสร็จเมื่อ:

- [ ] ใช้ Sentinel-2 L2A จริง
- [ ] scene ครอบ AOI จริง
- [ ] RGB/NIR band order ถูกต้อง
- [ ] inference 4x ทำสำเร็จ
- [ ] native และ SR ใช้ extent เดียวกัน
- [ ] display stretch เดียวกัน
- [ ] output ไม่ดำ/ไม่ flat
- [ ] metadata บันทึก scene ID และ acquisition date
- [ ] multi-plot dataset ไม่มีแปลง missing
- [ ] web selector/swipe/zoom ใช้งานได้ถ้าผู้ใช้ขอเว็บ
- [ ] ทำใน branch/path แยกหากมีของเดิม
- [ ] deployment เป็น READY ก่อนส่งลิงก์
- [ ] ไม่เขียน claim เกินสิ่งที่ output พิสูจน์ได้

---

# Quick execution recipe

เมื่อผู้ใช้สั่งสั้น ๆ ว่า:

> เพิ่ม resolution Sentinel ของพื้นที่นี้แล้วเอาขึ้นเว็บ

ให้ทำตามนี้ทันที:

1. หา AOI จากไฟล์/plot ที่มีอยู่
2. สร้าง branch แยก
3. search Sentinel-2 scene ที่ครอบ AOI และ cloud ต่ำ
4. อ่าน B04/B03/B02/B08 ที่ 10 m เป็น `[R,G,B,NIR]`
5. ตรวจ valid pixel fraction
6. run `geoai.super_resolution()` scale 4
7. สร้าง native/SR WebP extent เดียวกัน
8. validate ไม่ดำ/ไม่ flat
9. เขียน `summary.json`
10. ถ้าหลายแปลง ใช้ matrix + artifact + single publish job
11. เพิ่ม plot selector + swipe + zoom ในเว็บแยก
12. deploy preview
13. ตรวจ deployment `READY`
14. ส่งลิงก์ให้ผู้ใช้

อย่าหยุดที่การเขียน script ถ้าผู้ใช้ขอผลบนเว็บ ต้อง run, validate และ publish ให้จบ
