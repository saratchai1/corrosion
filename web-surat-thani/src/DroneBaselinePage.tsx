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

type CandidateCrop = {
  asset: string
  marker: { x_percent: number; y_percent: number }
  coverage_status?: string
}

type AccretionCandidate = {
  transect_id: string
  historical_classification_1985_2026: string
  historical_net_change_m_1985_2026: number
  historical_rate_m_per_year_1985_2026: number
  historical_confidence: string
  baseline_waterline_2023_2026: {
    position_2023_m: number
    position_2026_m: number
    change_m: number
    direction: string
  }
  tide_matched_waterline_2023_2026: {
    position_2023_m: number
    position_2026_m: number
    change_m: number
    classification: string
    direction: string
  }
  candidate_zone: {
    center_lon: number
    center_lat: number
    waterline_point_2023_lon_lat: [number, number]
    waterline_point_2026_lon_lat: [number, number]
    inside_drone_extent: boolean
    drone_coverage_status?: string
    marker_on_full_same_extent: { x_percent: number; y_percent: number }
  }
  web_crops: {
    sentinel2_2023: CandidateCrop
    sentinel2_2026: CandidateCrop
    drone: CandidateCrop | null
  }
  post_2023_accretion_supported: boolean
  post_2023_verdict: string
  interpretation_th: string
}

type AccretionAudit = {
  plot_id: string
  question: string
  candidate_origin: string
  audit_period: string
  candidate_count: number
  post_2023_supported_candidate_count: number
  overall_verdict: string
  overall_interpretation_th: string
  coastal_vegetation_edge_project_median_change_2023_2026_m: number | null
  scientific_guard: string[]
  crop_method?: string
  same_extent: {
    bounds_wgs84: Bounds
    width_px: number
    height_px: number
    sentinel2_2023_asset: string
    sentinel2_2023_dates: string[]
    sentinel2_2026_asset: string
    drone_asset: string
  }
  candidates: AccretionCandidate[]
}

type Pan = { x: number; y: number }
type Drag = { pointerId: number; startX: number; startY: number; startPan: Pan } | null

function formatGiB(bytes: number) { return `${(bytes / 1024 ** 3).toFixed(2)} GiB` }
function formatPercent(value: number | null) { return value == null ? '—' : `${(value * 100).toFixed(2)}%` }
function formatGsd(value: number | null) { return value == null ? '—' : `${value.toFixed(3)} cm/px` }
function formatSignedMeters(value: number) { return `${value > 0 ? '+' : ''}${value.toFixed(2)} m` }

function CandidateImage({ crop, label, detail }: { crop: CandidateCrop; label: string; detail: string }) {
  return (
    <figure className="candidate-image">
      <div className="candidate-image-frame">
        <img src={crop.asset} alt={`${label} บริเวณ candidate ดินงอก 37-STC`} />
        <span
          className="candidate-ring"
          style={{ left: `${crop.marker.x_percent}%`, top: `${crop.marker.y_percent}%` }}
          aria-hidden="true"
        />
      </div>
      <figcaption><strong>{label}</strong><small>{detail}</small></figcaption>
    </figure>
  )
}

function DroneOutsideFootprint() {
  return (
    <figure className="candidate-image candidate-image-unavailable">
      <div className="candidate-unavailable"><strong>OUTSIDE DRONE FOOTPRINT</strong><span>ตำแหน่ง candidate อยู่นอกขอบภาพ GeoTIFF ที่ยืนยันแล้ว จึงไม่ใช้ภาพขอบ orthomosaic แทนตำแหน่งจริง</span></div>
      <figcaption><strong>Drone HR</strong><small>ไม่มี coverage ที่ candidate center</small></figcaption>
    </figure>
  )
}

export default function DroneBaselinePage() {
  const [manifest, setManifest] = useState<DroneManifest | null>(null)
  const [audit, setAudit] = useState<AccretionAudit | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState<Pan>({ x: 0, y: 0 })
  const [drag, setDrag] = useState<Drag>(null)
  const [comparePosition, setComparePosition] = useState(50)
  const stageRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    Promise.all([
      fetch('data/surat_thani/drone/drone_manifest.json').then((response) => {
        if (!response.ok) throw new Error(`drone_manifest HTTP ${response.status}`)
        return response.json()
      }),
      fetch('data/surat_thani/drone/land_accretion_candidate_audit.json').then((response) => {
        if (!response.ok) throw new Error(`land_accretion_candidate_audit HTTP ${response.status}`)
        return response.json()
      }),
    ])
      .then(([manifestValue, auditValue]) => {
        setManifest(manifestValue as DroneManifest)
        setAudit(auditValue as AccretionAudit)
      })
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

  if (error) return <main className="document-page"><section className="document-hero"><h1>ภาพโดรน HR</h1><p>โหลด evidence ไม่สำเร็จ: {error}</p></section></main>
  if (!manifest || !audit) return <main className="document-page"><section className="document-hero"><h1>ภาพโดรน HR</h1><p>กำลังเปิด high-resolution baseline และตรวจ candidate ดินงอก…</p></section></main>

  const compare = manifest.same_extent_compare?.status === 'AVAILABLE' ? manifest.same_extent_compare : null
  const qaPassed = manifest.qa.georeference_status === 'PASS_EXPECTED_PROJECT_CRS' && manifest.qa.imagery_coverage_status === 'PASS_GE_95PCT'
  const outsideDrone = audit.candidates.filter((candidate) => !candidate.candidate_zone.inside_drone_extent)

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

      <section className="accretion-audit">
        <div className="accretion-audit-head">
          <div>
            <span>LAND ACCRETION AUDIT · 2023 → 2026</span>
            <h2>2 จุดที่เคยดูเหมือน “ดินงอก” งอกหลังปลูกจริงไหม?</h2>
            <p>{audit.overall_interpretation_th}</p>
          </div>
          <div className="accretion-score">
            <strong>{audit.post_2023_supported_candidate_count}/{audit.candidate_count}</strong>
            <span>จุดที่ยังรองรับว่าเป็น candidate หลังปี 2023</span>
          </div>
        </div>

        <div className="audit-drone-overview" style={{ aspectRatio: `${audit.same_extent.width_px}/${audit.same_extent.height_px}` }}>
          <img src={audit.same_extent.drone_asset} alt="ภาพโดรน 37-STC พร้อมตำแหน่ง candidate ที่อยู่ภายใน footprint" />
          {audit.candidates.filter((candidate) => candidate.candidate_zone.inside_drone_extent).map((candidate) => (
            <span
              key={candidate.transect_id}
              className="audit-marker"
              style={{ left: `${candidate.candidate_zone.marker_on_full_same_extent.x_percent}%`, top: `${candidate.candidate_zone.marker_on_full_same_extent.y_percent}%` }}
            >
              <i />
              <b>{candidate.transect_id}</b>
            </span>
          ))}
          <div className="audit-overview-note">วงเฉพาะ candidate ที่อยู่ภายใน GeoTIFF ที่ยืนยันพิกัดแล้ว{outsideDrone.length ? ` · ${outsideDrone.map((item) => item.transect_id).join(', ')} อยู่นอก drone footprint` : ''}</div>
        </div>

        <div className="accretion-candidate-grid">
          {audit.candidates.map((candidate) => (
            <article className={`accretion-candidate ${candidate.post_2023_accretion_supported ? 'retained' : 'rejected'}`} key={candidate.transect_id}>
              <header>
                <div><span>TRANSECT</span><strong>{candidate.transect_id}</strong></div>
                <b>{candidate.post_2023_accretion_supported ? 'ยังเป็น candidate' : 'ไม่รองรับดินงอกหลัง 2023'}</b>
              </header>

              <div className="candidate-metrics">
                <div><span>ระยะยาว 1985→2026</span><strong className="positive">{formatSignedMeters(candidate.historical_net_change_m_1985_2026)}</strong><small>{candidate.historical_classification_1985_2026} · confidence {candidate.historical_confidence}</small></div>
                <div><span>Baseline 2023→2026</span><strong>{formatSignedMeters(candidate.baseline_waterline_2023_2026.change_m)}</strong><small>{candidate.baseline_waterline_2023_2026.direction}</small></div>
                <div><span>Tide-matched 2023→2026</span><strong>{formatSignedMeters(candidate.tide_matched_waterline_2023_2026.change_m)}</strong><small>{candidate.tide_matched_waterline_2023_2026.classification}</small></div>
              </div>

              <div className="candidate-image-grid">
                <CandidateImage crop={candidate.web_crops.sentinel2_2023} label="Sentinel-2 · 2023" detail={audit.same_extent.sentinel2_2023_dates.join(', ')} />
                <CandidateImage crop={candidate.web_crops.sentinel2_2026} label="Sentinel-2 · 2026" detail="crop รอบตำแหน่ง candidate จริง" />
                {candidate.web_crops.drone ? <CandidateImage crop={candidate.web_crops.drone} label="Drone HR" detail={`${formatGsd(manifest.qa.mean_gsd_cm)} · verified footprint`} /> : <DroneOutsideFootprint />}
              </div>

              <p className="candidate-verdict">{candidate.interpretation_th}</p>
              <small className="candidate-coordinate">candidate center: {candidate.candidate_zone.center_lat.toFixed(6)}, {candidate.candidate_zone.center_lon.toFixed(6)} · {candidate.candidate_zone.drone_coverage_status ?? (candidate.candidate_zone.inside_drone_extent ? 'INSIDE_DRONE' : 'OUTSIDE_DRONE')}</small>
            </article>
          ))}
        </div>

        <div className="audit-guard">
          <strong>ข้อสรุปสำหรับคำถาม “ดินงอกหลังปลูกไหม”</strong>
          <p>สองจุดนี้เคยถูกติดธงจากแนวโน้มยาว 1985–2026 แต่เมื่อจำกัดช่วงเป็น 2023–2026 ไม่มีจุดใดให้สัญญาณ seaward พร้อมกันทั้ง baseline และ tide-matched. จึงไม่ควรเรียกสองบริเวณนี้ว่า “ดินงอกหลังปลูก”. ขอบพืชชายฝั่งระดับ Sentinel-2 ของโครงการก็มี median change {audit.coastal_vegetation_edge_project_median_change_2023_2026_m ?? 0} m ในช่วงเดียวกัน.</p>
        </div>
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
