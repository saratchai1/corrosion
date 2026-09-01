import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'

type Bounds = { left: number; bottom: number; right: number; top: number }

type DroneManifest = {
  title: string
  plot_id: string
  status: string
  evidence_level: string
  one_epoch_guard: string
  source: {
    province_folder_id: string
    date_folder_id: string
    plot_folder_id: string
    folder_label: string
    folder_date_status: string
    raw_geotiff: {
      drive_file_id: string
      title: string
      size_bytes: number
      mime_type: string
      created_time_utc: string
      modified_time_utc: string
      drive_url: string
    }
    drive_preview: {
      drive_file_id: string
      title: string
      size_bytes: number
      content_status: string
      drive_url: string
    }
  }
  project_geometry_reference: {
    crs: string
    role: string
    raw_tiff_crs_assumed_from_project_geometry: boolean
    primary_area_rai: number
    guard: string
  }
  web_preview: { asset: string; width_px: number; height_px: number; derivation: string }
  same_extent_compare?: {
    status: string
    role: string
    bounds_wgs84: Bounds
    width_px: number
    height_px: number
    drone_asset: string
    sentinel2_asset: string
    sentinel2_target_year: number
    sentinel2_actual_year: number
    sentinel2_dates: string[]
    sentinel2_resolution_m: number
    registration_note: string
  }
  legacy_alignment_audit: {
    drive_folder_id: string
    status: string
    placeholder_asset_title: string
    html_labels_found: string[]
    reason: string
  }
  qa: {
    raw_download_status: string
    connected_drive_download_limit_bytes: number
    raw_geotiff_size_bytes: number
    georeference_status: string
    imagery_coverage_status: string
    cross_sensor_alignment_status: string
    crs: string | null
    mean_gsd_cm: number | null
    band_count: number | null
    valid_imagery_fraction: number | null
    nir_band_present: boolean | null
    drone_ndvi_supported: boolean | null
    inspection_script: string
    publish_script?: string
    raw_metadata_reason: string
  }
  scientific_guard: string[]
}

type Pan = { x: number; y: number }
type Drag = { pointerId: number; startX: number; startY: number; startPan: Pan } | null

function formatGiB(bytes: number) { return `${(bytes / 1024 ** 3).toFixed(2)} GiB` }
function formatPercent(value: number | null) { return value == null ? '—' : `${(value * 100).toFixed(2)}%` }
function formatGsd(value: number | null) { return value == null ? '—' : `${value.toFixed(3)} cm/px` }

export default function DroneBaselinePage() {
  const [manifest, setManifest] = useState<DroneManifest | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState<Pan>({ x: 0, y: 0 })
  const [drag, setDrag] = useState<Drag>(null)
  const [comparePosition, setComparePosition] = useState(50)
  const stageRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    fetch('data/surat_thani/drone/drone_manifest.json')
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        return response.json()
      })
      .then((value: unknown) => setManifest(value as DroneManifest))
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : String(reason)))
  }, [])

  const clampPan = (next: Pan) => {
    const stage = stageRef.current
    if (!stage || zoom <= 1) return { x: 0, y: 0 }
    const rect = stage.getBoundingClientRect()
    const maxX = rect.width * (zoom - 1) / 2
    const maxY = rect.height * (zoom - 1) / 2
    return { x: Math.max(-maxX, Math.min(maxX, next.x)), y: Math.max(-maxY, Math.min(maxY, next.y)) }
  }

  const setZoomLevel = (value: number) => {
    const next = Math.max(1, Math.min(4, Math.round(value * 2) / 2))
    setZoom(next)
    if (next === 1) setPan({ x: 0, y: 0 })
  }

  const pointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (zoom <= 1) return
    event.currentTarget.setPointerCapture(event.pointerId)
    setDrag({ pointerId: event.pointerId, startX: event.clientX, startY: event.clientY, startPan: pan })
  }
  const pointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!drag || drag.pointerId !== event.pointerId) return
    setPan(clampPan({ x: drag.startPan.x + event.clientX - drag.startX, y: drag.startPan.y + event.clientY - drag.startY }))
  }
  const pointerUp = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (drag?.pointerId === event.pointerId) {
      setDrag(null)
      if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
    }
  }

  if (error) return <main className="document-page"><section className="document-hero"><h1>ภาพโดรน HR</h1><p>โหลด manifest ไม่สำเร็จ: {error}</p></section></main>
  if (!manifest) return <main className="document-page"><section className="document-hero"><h1>ภาพโดรน HR</h1><p>กำลังเปิด high-resolution baseline…</p></section></main>

  const compare = manifest.same_extent_compare?.status === 'AVAILABLE' ? manifest.same_extent_compare : null
  const qaPassed = manifest.qa.georeference_status === 'PASS_EXPECTED_PROJECT_CRS' && manifest.qa.imagery_coverage_status === 'PASS_GE_95PCT'

  return (
    <main className="document-page drone-page">
      <section className="document-hero">
        <span>HIGH-RESOLUTION BASELINE · GEOREFERENCE QA</span>
        <h1>ภาพโดรน 37-STC</h1>
        <p>Raw GeoTIFF ถูกอ่านพิกัดจริงแล้วและใช้สร้างภาพเว็บจาก raster ต้นทางโดยตรง. หน้านี้ใช้เป็น baseline ความละเอียดสูง 1 epoch และมี Drone ↔ Sentinel-2 แบบขอบเขตเดียวกันสำหรับตรวจบริบทเชิงพื้นที่ แต่ยังไม่ใช้คำนวณอัตรากัดเซาะจากโดรนเพียง epoch เดียว.</p>
      </section>

      <section className="drone-layout">
        <article className="drone-viewer-card">
          <div className="drone-toolbar">
            <div><span>37-STC ORTHOMOSAIC · GEOREFERENCED</span><strong>Raw GeoTIFF-derived web preview</strong></div>
            <div className="zoom-controls"><button type="button" onClick={() => setZoomLevel(zoom - 0.5)}>−</button><span>{Math.round(zoom * 100)}%</span><button type="button" onClick={() => setZoomLevel(zoom + 0.5)}>+</button><button type="button" onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }) }}>Reset</button></div>
          </div>
          <div
            ref={stageRef}
            className={`drone-preview-stage ${zoom > 1 ? 'pannable' : ''} ${drag ? 'panning' : ''}`}
            style={{ aspectRatio: `${manifest.web_preview.width_px}/${manifest.web_preview.height_px}` }}
            onPointerDown={pointerDown}
            onPointerMove={pointerMove}
            onPointerUp={pointerUp}
            onPointerCancel={pointerUp}
          >
            <img
              src={manifest.web_preview.asset}
              alt="orthomosaic ที่อ่าน georeference จาก raw GeoTIFF ของแปลง 37-STC สุราษฎร์ธานี"
              draggable={false}
              style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }}
            />
          </div>
          <p className="viewer-caption">{manifest.web_preview.derivation}</p>
        </article>

        <aside className="drone-facts">
          <article className={qaPassed ? 'passed' : 'pending'}><span>Raw georeference QA</span><strong>{manifest.qa.georeference_status}</strong><small>{manifest.qa.crs ?? '—'} · coverage {formatPercent(manifest.qa.valid_imagery_fraction)}</small></article>
          <article><span>Ground sampling distance</span><strong>{formatGsd(manifest.qa.mean_gsd_cm)}</strong><small>{manifest.qa.band_count ?? '—'} bands · {manifest.qa.nir_band_present === false ? 'RGB + Alpha · ไม่มี NIR' : 'band config pending'}</small></article>
          <article><span>Raw source</span><strong>{manifest.source.raw_geotiff.title}</strong><small>{formatGiB(manifest.source.raw_geotiff.size_bytes)} · raw TIFF ไม่ถูกเสิร์ฟขึ้นเว็บ</small></article>
          <article><span>Folder label</span><strong>{manifest.source.folder_label}</strong><small>{manifest.source.folder_date_status} — ยังไม่ถือเป็น flight date ที่ยืนยันแล้ว</small></article>
          <article><span>Cross-sensor compare</span><strong>{manifest.qa.cross_sensor_alignment_status}</strong><small>{compare ? 'same WGS84 extent / same pixel dimensions' : 'ยังไม่มี asset'}</small></article>
          <a className="drive-button" href={manifest.source.raw_geotiff.drive_url} target="_blank" rel="noreferrer">เปิด raw GeoTIFF บน Google Drive</a>
        </aside>
      </section>

      {compare ? (
        <section className="drone-compare-card">
          <div className="drone-compare-head">
            <div><span>SAME-EXTENT VISUAL CHECK</span><strong>Sentinel-2 {compare.sentinel2_target_year} ↔ Drone HR</strong></div>
            <small>{compare.width_px} × {compare.height_px}px · Sentinel {compare.sentinel2_resolution_m} m · Drone {formatGsd(manifest.qa.mean_gsd_cm)}</small>
          </div>
          <div className="drone-compare-stage" style={{ aspectRatio: `${compare.width_px}/${compare.height_px}` }}>
            <img className="drone-compare-base" src={compare.sentinel2_asset} alt={`Sentinel-2 ${compare.sentinel2_target_year} ในขอบเขตเดียวกับภาพโดรน`} />
            <div className="drone-compare-overlay" style={{ clipPath: `inset(0 0 0 ${comparePosition}%)` }}>
              <img src={compare.drone_asset} alt="ภาพโดรนในขอบเขตเดียวกับ Sentinel-2" />
            </div>
            <span className="compare-label compare-label-left">Sentinel-2 {compare.sentinel2_target_year}</span>
            <span className="compare-label compare-label-right">Drone HR</span>
            <div className="drone-compare-divider" style={{ left: `${comparePosition}%` }}><i>↔</i></div>
          </div>
          <label className="drone-compare-control">
            <span>ลากเพื่อเทียบ Sentinel-2 ↔ Drone</span>
            <input type="range" min={0} max={100} value={comparePosition} onChange={(event) => setComparePosition(Number(event.target.value))} aria-label="สัดส่วนการเปรียบเทียบ Sentinel-2 กับภาพโดรน" />
          </label>
          <p>{compare.registration_note}</p>
          <small>Sentinel scenes: {compare.sentinel2_dates.join(', ')}</small>
        </section>
      ) : (
        <section className="comparison-lock">
          <div><span>CROSS-SENSOR ALIGNMENT</span><strong>{manifest.qa.cross_sensor_alignment_status}</strong></div>
          <p>GeoTIFF QA ยังไม่พร้อมสำหรับการสร้าง same-extent comparison.</p>
        </section>
      )}

      <section className="two-column-copy">
        <article>
          <h2>QA ที่ผ่านแล้ว</h2>
          <ul>
            <li>อ่าน CRS จาก raw GeoTIFF โดยตรง: <strong>{manifest.qa.crs ?? '—'}</strong></li>
            <li>GSD เฉลี่ย: <strong>{formatGsd(manifest.qa.mean_gsd_cm)}</strong></li>
            <li>ความครอบคลุมภาพภายในขอบแปลง 37-STC: <strong>{formatPercent(manifest.qa.valid_imagery_fraction)}</strong></li>
            <li>Band configuration: <strong>{manifest.qa.band_count} bands, RGB + Alpha</strong>; ไม่มี NIR จึงไม่คำนวณ drone NDVI</li>
            <li>Legacy placeholder ถูกปฏิเสธ: <strong>{manifest.legacy_alignment_audit.status}</strong></li>
          </ul>
        </article>
        <article>
          <h2>ข้อจำกัดที่ยังต้องรักษา</h2>
          <ul>{manifest.scientific_guard.map((item) => <li key={item}>{item}</li>)}</ul>
        </article>
      </section>
    </main>
  )
}
