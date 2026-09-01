import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from 'react'
import { createPortal } from 'react-dom'
import './droneBaseline.css'

type AlignmentPlot = {
  plot_id: string
  drone_preview: string
  sentinel2_preview: string
  overlay_svg: string
  drone_gsd_cm: number
  sentinel2_native_resolution_m: number
  linear_resolution_ratio_sentinel_to_drone: number
  drone_extent_epsg32647: number[]
  canvas_width: number
  canvas_height: number
  sentinel2_valid_fraction_on_drone_extent: number
  imagery_coverage_status: string
}

type DronePlot = {
  plot_id: string
  drive_title: string
  size_bytes: number
  crs: string
  width_px: number
  height_px: number
  band_count: number
  mean_gsd_cm: number
  plot_valid_image_fraction: number
  georeference_status: string
  imagery_coverage_status: string
  analysis_readiness: string
  folder_date_iso: string
  folder_date_status: string
  flight_date_verified: boolean
  verified_planting_completion_date: string | null
  provisional_days_from_completion: number | null
  provisional_planting_phase: string
  preview: string
}

export type DroneBaselineSummary = {
  title: string
  orthomosaic_count: number
  plot_ids: string[]
  total_source_size_gib: number
  common_crs: string[]
  gsd_cm_range: [number, number]
  qa: {
    all_georeference_pass: boolean
    georeference_pass_count: number
    coverage_complete_count: number
    coverage_partial_usable_count: number
    coverage_partial_usable_plot_ids: string[]
    coverage_insufficient_count: number
    usable_plot_count: number
    interpretation: string
  }
  date_evidence: {
    folder_labels: string[]
    status: string
    interpretation: string
  }
  raster_band_scope: {
    band_count: number
    interpretation: string[]
    nir_band_present: boolean
    drone_ndvi_supported: boolean
    scientific_guard: string
  }
  baseline_readiness: {
    status: string
    usable_plot_count: number
    partial_coverage_plot_ids: string[]
    what_this_adds: string
    what_it_does_not_add: string
  }
  plots: DronePlot[]
  sentinel2_alignment: {
    purpose: string
    plot_count: number
    drone_source_date: string
    drone_source_date_status: string
    sentinel2_scene_id: string
    sentinel2_scene_date: string
    sentinel2_tide_level_m_msl: number
    provisional_day_gap: number
    scientific_guard: string
    plots: AlignmentPlot[]
  }
}

type Props = {
  summary: DroneBaselineSummary
}

type Pan = { x: number; y: number }

type PanDrag = {
  pointerId: number
  startX: number
  startY: number
  startPan: Pan
} | null

function formatSize(gib: number): string {
  return `${gib.toFixed(2)} GiB`
}

function percent(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

function formatThaiDate(value: string | null): string {
  if (!value) return '—'
  const [year, month, day] = value.split('-').map(Number)
  return new Intl.DateTimeFormat('th-TH', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(Date.UTC(year, month - 1, day)))
}

function coverageLabel(status: string): string {
  if (status === 'COMPLETE_GE_95PCT') return 'coverage ≥95%'
  if (status === 'PARTIAL_USABLE_90_TO_95PCT') return 'coverage บางส่วน แต่ใช้ได้'
  return 'ต้องตรวจ coverage'
}

function CrossSensorCompare({
  alignment,
  plot,
}: {
  alignment: AlignmentPlot
  plot: DronePlot
}) {
  const stageRef = useRef<HTMLDivElement | null>(null)
  const [split, setSplit] = useState(50)
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState<Pan>({ x: 0, y: 0 })
  const [panDrag, setPanDrag] = useState<PanDrag>(null)
  const [overlay, setOverlay] = useState(true)

  useEffect(() => {
    setSplit(50)
    setZoom(1)
    setPan({ x: 0, y: 0 })
    setPanDrag(null)
  }, [alignment.plot_id])

  const clampPan = (next: Pan): Pan => {
    const stage = stageRef.current
    if (!stage || zoom <= 1) return { x: 0, y: 0 }
    const rect = stage.getBoundingClientRect()
    const maxX = rect.width * (zoom - 1) / 2
    const maxY = rect.height * (zoom - 1) / 2
    return {
      x: Math.max(-maxX, Math.min(maxX, next.x)),
      y: Math.max(-maxY, Math.min(maxY, next.y)),
    }
  }

  const updateSplit = (clientX: number) => {
    const stage = stageRef.current
    if (!stage) return
    const rect = stage.getBoundingClientRect()
    const value = (clientX - rect.left) / Math.max(rect.width, 1) * 100
    setSplit(Math.max(0, Math.min(100, value)))
  }

  const onStagePointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if ((event.target as Element).closest('.drone-compare-controls, .drone-divider')) return
    if (zoom <= 1.001) {
      updateSplit(event.clientX)
      return
    }
    event.currentTarget.setPointerCapture(event.pointerId)
    setPanDrag({
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      startPan: pan,
    })
  }

  const onStagePointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!panDrag || panDrag.pointerId !== event.pointerId) return
    setPan(clampPan({
      x: panDrag.startPan.x + event.clientX - panDrag.startX,
      y: panDrag.startPan.y + event.clientY - panDrag.startY,
    }))
  }

  const onStagePointerUp = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (panDrag?.pointerId === event.pointerId) {
      setPanDrag(null)
      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId)
      }
    }
  }

  const onDividerPointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.stopPropagation()
    event.currentTarget.setPointerCapture(event.pointerId)
    updateSplit(event.clientX)
  }

  const onDividerPointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!event.currentTarget.hasPointerCapture(event.pointerId)) return
    event.preventDefault()
    event.stopPropagation()
    updateSplit(event.clientX)
  }

  const setZoomLevel = (next: number) => {
    const value = Math.max(1, Math.min(4, Math.round(next * 2) / 2))
    setZoom(value)
    if (value === 1) setPan({ x: 0, y: 0 })
    else window.requestAnimationFrame(() => setPan((current) => clampPan(current)))
  }

  const resetView = () => {
    setZoom(1)
    setPan({ x: 0, y: 0 })
  }

  const transform = `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`
  const aspectRatio = `${alignment.canvas_width} / ${alignment.canvas_height}`

  return (
    <div className="drone-compare-wrap">
      <div className="drone-compare-toolbar">
        <div>
          <strong>{alignment.plot_id}</strong>
          <span>Drone {alignment.drone_gsd_cm.toFixed(2)} ซม./px · Sentinel-2 10 ม./px</span>
        </div>
        <div className="drone-layer-legend">
          <span><i className="plot" />ขอบแปลง</span>
          <span><i className="water" />Waterline 2025</span>
          <span><i className="mangrove" />ขอบพืช proxy 2025</span>
        </div>
      </div>

      <div
        ref={stageRef}
        className={`drone-compare-stage ${zoom > 1 ? 'pannable' : ''} ${panDrag ? 'panning' : ''}`}
        style={{ aspectRatio }}
        onPointerDown={onStagePointerDown}
        onPointerMove={onStagePointerMove}
        onPointerUp={onStagePointerUp}
        onPointerCancel={onStagePointerUp}
      >
        <div className="drone-compare-layer after" style={{ transform }}>
          <img src={alignment.sentinel2_preview} alt={`Sentinel-2 2025 aligned to ${alignment.plot_id}`} draggable={false} />
        </div>
        <div
          className="drone-before-clip"
          style={{ clipPath: `inset(0 ${100 - split}% 0 0)` }}
        >
          <div className="drone-compare-layer before" style={{ transform }}>
            <img src={alignment.drone_preview} alt={`Drone orthomosaic ${alignment.plot_id}`} draggable={false} />
          </div>
        </div>
        {overlay && (
          <div className="drone-vector-layer" style={{ transform }}>
            <img src={alignment.overlay_svg} alt="" aria-hidden="true" draggable={false} />
          </div>
        )}

        <div
          className="drone-divider"
          style={{ left: `${split}%` }}
          onPointerDown={onDividerPointerDown}
          onPointerMove={onDividerPointerMove}
        >
          <span>↔</span>
        </div>

        <div className="drone-side-label left"><span>DRONE</span><strong>Orthomosaic</strong></div>
        <div className="drone-side-label right"><span>SENTINEL-2</span><strong>14 ก.พ. 2025</strong></div>

        <div className="drone-compare-controls" onPointerDown={(event) => event.stopPropagation()}>
          <button type="button" onClick={() => setZoomLevel(zoom - 0.5)} disabled={zoom <= 1}>−</button>
          <button type="button" className="zoom-readout" onClick={resetView}>{Math.round(zoom * 100)}%</button>
          <button type="button" onClick={() => setZoomLevel(zoom + 0.5)} disabled={zoom >= 4}>+</button>
          <button type="button" className={overlay ? 'active' : ''} onClick={() => setOverlay((value) => !value)}>
            เส้น {overlay ? 'เปิด' : 'ปิด'}
          </button>
        </div>

        {zoom > 1 && <div className="drone-pan-hint">ลากพื้นภาพเพื่อเลื่อน · ลาก ↔ เพื่อเทียบภาพ</div>}
      </div>

      <div className="drone-compare-caption">
        <div><strong>ความละเอียดเชิงเส้น</strong><span>โดรนละเอียดกว่า Sentinel-2 ประมาณ {alignment.linear_resolution_ratio_sentinel_to_drone.toFixed(0)}×</span></div>
        <div><strong>Coverage ในแปลง</strong><span>{percent(plot.plot_valid_image_fraction)} · {coverageLabel(plot.imagery_coverage_status)}</span></div>
        <div><strong>Sentinel-2 ระดับน้ำ</strong><span>ภาพที่คัดระดับน้ำแล้ว · 0.885 m MSL</span></div>
      </div>
    </div>
  )
}

function DroneBaselinePanel({ summary }: Props) {
  const alignments = summary.sentinel2_alignment.plots
  const initial = alignments.some((item) => item.plot_id === '91-STC') ? '91-STC' : alignments[0]?.plot_id ?? ''
  const [plotId, setPlotId] = useState(initial)
  const alignment = alignments.find((item) => item.plot_id === plotId) ?? alignments[0]
  const plot = summary.plots.find((item) => item.plot_id === alignment?.plot_id) ?? summary.plots[0]

  const plantingNote = useMemo(() => {
    if (!plot?.verified_planting_completion_date) return null
    if (plot.provisional_days_from_completion == null) return null
    return `ถ้าชื่อโฟลเดอร์ 25-12-2567 คือวันบินจริง ภาพนี้จะอยู่ ${plot.provisional_days_from_completion} วันหลังปลูกเสร็จ ${formatThaiDate(plot.verified_planting_completion_date)}`
  }, [plot])

  if (!alignment || !plot) return null

  return (
    <section className="drone-baseline-panel" id="drone-baseline">
      <header className="drone-baseline-header">
        <div>
          <span>NEW EVIDENCE · DRONE ORTHOMOSAIC · 9 PLOTS</span>
          <h2>โดรนทุกแปลงพร้อมเป็น High-resolution baseline แล้ว</h2>
          <p>
            ตรวจ raw GeoTIFF จาก Shared Drive โดยตรงครบ 9 แปลง ไม่ย้ายเข้า My Drive และไม่เก็บไฟล์ 13.4 GiB ใน GitHub
            ทุกไฟล์มีพิกัด EPSG:32647 ตรงกับพื้นที่โครงการ และถูกทำ preview เบาสำหรับตรวจเทียบกับ Sentinel-2
          </p>
        </div>
        <div className="drone-baseline-badge">
          <strong>{summary.qa.georeference_pass_count}/9</strong>
          <span>Georeference PASS</span>
          <small>{summary.baseline_readiness.status.replaceAll('_', ' ')}</small>
        </div>
      </header>

      <div className="drone-baseline-kpis">
        <article><span>GeoTIFF ต้นฉบับ</span><strong>{summary.orthomosaic_count}</strong><small>{formatSize(summary.total_source_size_gib)}</small></article>
        <article><span>CRS</span><strong>32647</strong><small>WGS 84 / UTM zone 47N</small></article>
        <article><span>GSD</span><strong>{summary.gsd_cm_range[0].toFixed(2)}–{summary.gsd_cm_range[1].toFixed(2)}</strong><small>เซนติเมตร / pixel</small></article>
        <article className="good"><span>Coverage ≥95%</span><strong>{summary.qa.coverage_complete_count}</strong><small>8 แปลง complete</small></article>
        <article className="caution"><span>Partial coverage</span><strong>{summary.qa.coverage_partial_usable_count}</strong><small>91-STC = 92.68%</small></article>
        <article><span>Band</span><strong>RGB+A</strong><small>ไม่มี NIR · ทำ drone NDVI ไม่ได้</small></article>
      </div>

      <div className="drone-baseline-callouts">
        <article className="positive">
          <span>สิ่งที่เพิ่มขึ้นจากข้อมูลชุดนี้</span>
          <strong>ตรวจขอบแปลง / ขอบพืช / ขอบตลิ่งได้ละเอียดระดับเซนติเมตร</strong>
          <p>ใช้เป็น baseline เพื่อตรวจจุดที่ Sentinel-2 เคยให้สัญญาณผิดปกติ และวางตำแหน่ง BANK_EDGE / MANGROVE_EDGE สำหรับการบินซ้ำครั้งถัดไป</p>
        </article>
        <article className="guard">
          <span>ยังไม่ใช่อัตราการกัดเซาะจากโดรน</span>
          <strong>ตอนนี้มี orthomosaic เพียง 1 epoch</strong>
          <p>ต้องมีโดรนรอบที่สองในอนาคตจึงคำนวณการเคลื่อนของขอบตลิ่ง/ขอบป่าด้วยความละเอียดสูงได้ ส่วนชื่อโฟลเดอร์ 25-12-2567 ยังไม่ถือเป็นวันบินที่ยืนยันแล้ว</p>
        </article>
      </div>

      <div className="drone-plot-tabs" role="tablist" aria-label="เลือกแปลงโดรน">
        {alignments.map((item) => {
          const itemPlot = summary.plots.find((row) => row.plot_id === item.plot_id)
          return (
            <button
              type="button"
              key={item.plot_id}
              className={item.plot_id === alignment.plot_id ? 'active' : ''}
              onClick={() => setPlotId(item.plot_id)}
            >
              <strong>{item.plot_id}</strong>
              <span>{item.drone_gsd_cm.toFixed(2)} cm/px</span>
              <small>{itemPlot ? percent(itemPlot.plot_valid_image_fraction) : '—'} coverage</small>
            </button>
          )
        })}
      </div>

      <CrossSensorCompare alignment={alignment} plot={plot} />

      <div className="drone-evidence-note">
        <div>
          <strong>เรื่องวันบิน</strong>
          <p>{summary.date_evidence.interpretation}</p>
          {plantingNote && <em>{plantingNote} — ข้อความนี้ยังเป็น conditional จนกว่าจะยืนยัน flight date</em>}
        </div>
        <div>
          <strong>เรื่อง NDVI</strong>
          <p>{summary.raster_band_scope.scientific_guard}</p>
        </div>
        <div>
          <strong>เรื่อง Sentinel-2</strong>
          <p>{summary.sentinel2_alignment.scientific_guard}</p>
        </div>
      </div>
    </section>
  )
}

export default function DroneBaselineInjector({ summary }: Props) {
  const [mount, setMount] = useState<HTMLElement | null>(null)

  useEffect(() => {
    const compare = document.querySelector<HTMLElement>('.spectral-compare')
    const parent = compare?.parentElement
    if (!compare || !parent) return
    const node = document.createElement('div')
    node.className = 'drone-baseline-portal'
    parent.insertBefore(node, compare)
    setMount(node)
    return () => {
      setMount(null)
      node.remove()
    }
  }, [])

  return mount ? createPortal(<DroneBaselinePanel summary={summary} />, mount) : null
}
