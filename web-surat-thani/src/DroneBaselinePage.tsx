import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'

type DroneManifest = {
  title: string
  plot_id: string
  evidence_level: string
  one_epoch_guard: string
  source: {
    province_folder_id: string
    date_folder_id: string
    plot_folder_id: string
    folder_label: string
    folder_date_status: string
    raw_geotiff: { drive_file_id: string; title: string; size_bytes: number; mime_type: string; drive_url: string }
    drive_preview: { drive_file_id: string; title: string; size_bytes: number; drive_url: string }
  }
  web_preview: { asset: string; width_px: number; height_px: number; derivation: string }
  qa: {
    georeference_status: string
    imagery_coverage_status: string
    crs: string | null
    mean_gsd_cm: number | null
    band_count: number | null
    raw_metadata_reason: string
  }
  scientific_guard: string[]
}

type Pan = { x: number; y: number }
type Drag = { pointerId: number; startX: number; startY: number; startPan: Pan } | null

function formatGiB(bytes: number) { return `${(bytes / 1024 ** 3).toFixed(2)} GiB` }

export default function DroneBaselinePage() {
  const [manifest, setManifest] = useState<DroneManifest | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState<Pan>({ x: 0, y: 0 })
  const [drag, setDrag] = useState<Drag>(null)
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

  return (
    <main className="document-page drone-page">
      <section className="document-hero">
        <span>HIGH-RESOLUTION BASELINE · SEPARATE EVIDENCE PAGE</span>
        <h1>ภาพโดรน 37-STC</h1>
        <p>ภาพนี้เป็น baseline ความละเอียดสูง 1 epoch แยกจากประวัติ Sentinel-2 โดยตั้งใจ ตาม SKILL.md เพื่อไม่ให้ความละเอียดเชิงพื้นที่ถูกตีความเป็นหลักฐานการเปลี่ยนแปลงตามเวลา.</p>
      </section>

      <section className="drone-layout">
        <article className="drone-viewer-card">
          <div className="drone-toolbar">
            <div><span>37-STC ORTHOMOSAIC PREVIEW</span><strong>Visual baseline</strong></div>
            <div className="zoom-controls"><button type="button" onClick={() => setZoomLevel(zoom - 0.5)}>−</button><span>{Math.round(zoom * 100)}%</span><button type="button" onClick={() => setZoomLevel(zoom + 0.5)}>+</button><button type="button" onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }) }}>Reset</button></div>
          </div>
          <div
            ref={stageRef}
            className={`drone-preview-stage ${zoom > 1 ? 'pannable' : ''} ${drag ? 'panning' : ''}`}
            onPointerDown={pointerDown}
            onPointerMove={pointerMove}
            onPointerUp={pointerUp}
            onPointerCancel={pointerUp}
          >
            <img
              src={manifest.web_preview.asset}
              alt="ภาพตัวอย่าง orthomosaic ของแปลง 37-STC สุราษฎร์ธานี"
              draggable={false}
              style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }}
            />
          </div>
          <p className="viewer-caption">Preview นี้ derive จากไฟล์ PNG ใน Google Drive เพื่อใช้บนเว็บเท่านั้น ไม่ใช้แทน raw GeoTIFF สำหรับ georeference QA.</p>
        </article>

        <aside className="drone-facts">
          <article><span>Evidence level</span><strong>{manifest.evidence_level}</strong><small>{manifest.one_epoch_guard}</small></article>
          <article><span>Raw source</span><strong>{manifest.source.raw_geotiff.title}</strong><small>{formatGiB(manifest.source.raw_geotiff.size_bytes)} · {manifest.source.raw_geotiff.mime_type}</small></article>
          <article><span>Folder label</span><strong>{manifest.source.folder_label}</strong><small>{manifest.source.folder_date_status}</small></article>
          <article className="pending"><span>Georeference QA</span><strong>{manifest.qa.georeference_status}</strong><small>{manifest.qa.raw_metadata_reason}</small></article>
          <article className="pending"><span>CRS / GSD / bands</span><strong>รอตรวจ raw metadata</strong><small>ไม่เดาค่าจากชื่อ folder หรือ preview image</small></article>
          <a className="drive-button" href={manifest.source.raw_geotiff.drive_url} target="_blank" rel="noreferrer">เปิด raw GeoTIFF บน Google Drive</a>
          <a className="drive-button secondary" href={manifest.source.drive_preview.drive_url} target="_blank" rel="noreferrer">เปิด PNG ต้นทางบน Google Drive</a>
        </aside>
      </section>

      <section className="comparison-lock">
        <div><span>CROSS-SENSOR ALIGNMENT</span><strong>LOCKED UNTIL GEOREFERENCE QA</strong></div>
        <p>ยังไม่วาง Drone ↔ Sentinel-2 แบบ same extent เพราะ connector ดาวน์โหลด GeoTIFF 3.33 GB เพื่ออ่าน CRS/GSD/transform ไม่ได้ในรอบนี้ การวางภาพให้ดูตรงกันด้วยตาโดยไม่มี metadata จะสร้างหลักฐานลวง จึงตั้งใจล็อก feature นี้ไว้ก่อน.</p>
      </section>

      <section className="two-column-copy">
        <article><h2>ใช้ภาพนี้ทำอะไรได้</h2><ul><li>ตรวจรายละเอียดเชิงภาพของ canopy / mudflat / channel / สิ่งกีดขวางใน baseline</li><li>ใช้เป็นหลักฐาน spatial context ความละเอียดสูง</li><li>ใช้วางแผนตำแหน่ง UAV/field validation รอบถัดไป</li></ul></article>
        <article><h2>ยังใช้ทำอะไรไม่ได้</h2><ul>{manifest.scientific_guard.map((item) => <li key={item}>{item}</li>)}</ul></article>
      </section>
    </main>
  )
}
