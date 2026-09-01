import { useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import DroneBaselinePage from './DroneBaselinePage'
import './drone-multiyear.css'

type CompareChoice = {
  id: string
  targetYear: number
  actualYear: number
  label: string
  sensor: string
  dates: string[]
  resolutionM: number
  asset: string
  period: string
}

type CompareCatalog = {
  title: string
  status: string
  bounds_wgs84: { left: number; bottom: number; right: number; top: number }
  width_px: number
  height_px: number
  defaultLeftId: string
  defaultRightId: string
  leftChoices: CompareChoice[]
  rightChoices: Array<{
    id: string
    label: string
    asset: string
    note: string
  }>
}

type ImageMode = 'natural' | 'vivid' | 'mono' | 'cool'
type ThemeMode = 'ocean' | 'mangrove' | 'slate'

const imageModes: Array<{ id: ImageMode; label: string; note: string }> = [
  { id: 'natural', label: 'Natural', note: 'สีภาพต้นฉบับ' },
  { id: 'vivid', label: 'Vivid', note: 'เพิ่ม contrast/saturation เพื่อดูขอบเขตง่ายขึ้น' },
  { id: 'mono', label: 'B&W', note: 'ขาวดำสำหรับดู texture/edge' },
  { id: 'cool', label: 'Cool', note: 'โทนเย็นสำหรับแยกน้ำ–แผ่นดินด้วยสายตา' },
]

const themes: Array<{ id: ThemeMode; label: string }> = [
  { id: 'ocean', label: 'Ocean' },
  { id: 'mangrove', label: 'Mangrove' },
  { id: 'slate', label: 'Slate' },
]

function imageFilter(mode: ImageMode) {
  if (mode === 'vivid') return 'saturate(1.3) contrast(1.12) brightness(1.02)'
  if (mode === 'mono') return 'grayscale(1) contrast(1.12)'
  if (mode === 'cool') return 'saturate(.9) contrast(1.08) hue-rotate(12deg) brightness(1.03)'
  return 'none'
}

export default function DroneMultiYearPage() {
  const [catalog, setCatalog] = useState<CompareCatalog | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [leftId, setLeftId] = useState('')
  const [rightId, setRightId] = useState('')
  const [position, setPosition] = useState(50)
  const [mode, setMode] = useState<ImageMode>('natural')
  const [theme, setTheme] = useState<ThemeMode>('ocean')
  const [dragging, setDragging] = useState(false)
  const stageRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    fetch('data/surat_thani/drone/compare_catalog.json')
      .then((response) => {
        if (!response.ok) throw new Error(`compare_catalog HTTP ${response.status}`)
        return response.json()
      })
      .then((value: unknown) => {
        const next = value as CompareCatalog
        setCatalog(next)
        setLeftId(next.defaultLeftId || next.leftChoices[0]?.id || '')
        setRightId(next.defaultRightId || next.rightChoices[0]?.id || '')
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : String(reason)))
  }, [])

  const left = useMemo(() => catalog?.leftChoices.find((item) => item.id === leftId) ?? null, [catalog, leftId])
  const right = useMemo(() => catalog?.rightChoices.find((item) => item.id === rightId) ?? null, [catalog, rightId])

  const setPositionFromPointer = (event: ReactPointerEvent<HTMLDivElement>) => {
    const stage = stageRef.current
    if (!stage) return
    const rect = stage.getBoundingClientRect()
    const next = ((event.clientX - rect.left) / Math.max(1, rect.width)) * 100
    setPosition(Math.max(0, Math.min(100, next)))
  }

  const pointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId)
    setDragging(true)
    setPositionFromPointer(event)
  }

  const pointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!dragging) return
    setPositionFromPointer(event)
  }

  const pointerUp = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
    setDragging(false)
    setPositionFromPointer(event)
  }

  if (error) {
    return <main className="multi-compare-loading"><strong>โหลด Multi-year compare ไม่สำเร็จ</strong><span>{error}</span></main>
  }
  if (!catalog || !left || !right) return <main className="multi-compare-loading">กำลังเตรียมภาพหลายปี…</main>

  const filter = imageFilter(mode)
  const activeImageMode = imageModes.find((item) => item.id === mode) ?? imageModes[0]

  return (
    <div className={`drone-multiyear-page compare-theme-${theme}`}>
      <section className="multi-compare-panel">
        <div className="multi-compare-head">
          <div>
            <span>SAME-EXTENT MULTI-YEAR VISUAL CHECK</span>
            <h1>{left.label} ↔ {right.label}</h1>
          </div>
          <div className="multi-compare-meta">
            <strong>{catalog.width_px} × {catalog.height_px}px</strong>
            <small>ขอบเขตเดียวกันทุกปี · visual comparison</small>
          </div>
        </div>

        <div className="multi-compare-controlbar">
          <label className="multi-control">
            <span>ด้านซ้าย · ย้อนหลัง</span>
            <select value={leftId} onChange={(event) => setLeftId(event.target.value)}>
              {catalog.leftChoices.map((item) => (
                <option key={item.id} value={item.id}>{item.label}</option>
              ))}
            </select>
            <small>{left.sensor} · ภาพจริง {left.actualYear} · {left.dates.length} scenes</small>
          </label>

          <label className="multi-control">
            <span>ด้านขวา · ปัจจุบัน</span>
            <select value={rightId} onChange={(event) => setRightId(event.target.value)}>
              {catalog.rightChoices.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
            </select>
            <small>{right.note}</small>
          </label>

          <div className="multi-control visual-mode-control">
            <span>โหมดสีภาพ</span>
            <div className="mode-buttons">
              {imageModes.map((item) => (
                <button type="button" key={item.id} className={mode === item.id ? 'active' : ''} onClick={() => setMode(item.id)}>{item.label}</button>
              ))}
            </div>
            <small>{activeImageMode.note} · visual only ไม่ใช่ NDVI/False Color</small>
          </div>

          <div className="multi-control theme-control">
            <span>สีหน้าเว็บ</span>
            <div className="theme-buttons">
              {themes.map((item) => (
                <button type="button" key={item.id} className={theme === item.id ? 'active' : ''} onClick={() => setTheme(item.id)}>{item.label}</button>
              ))}
            </div>
            <small>เปลี่ยนเฉพาะ UI ไม่เปลี่ยนข้อมูล</small>
          </div>
        </div>

        <div
          ref={stageRef}
          className={`multi-compare-stage ${dragging ? 'dragging' : ''}`}
          style={{ aspectRatio: `${catalog.width_px}/${catalog.height_px}` }}
          onPointerDown={pointerDown}
          onPointerMove={pointerMove}
          onPointerUp={pointerUp}
          onPointerCancel={pointerUp}
        >
          <img className="multi-image base" src={left.asset} alt={left.label} style={{ filter }} draggable={false} />
          <div className="multi-image-overlay" style={{ clipPath: `inset(0 0 0 ${position}%)` }}>
            <img className="multi-image" src={right.asset} alt={right.label} style={{ filter }} draggable={false} />
          </div>
          <span className="multi-badge left">{left.label}</span>
          <span className="multi-badge right">{right.label}</span>
          <div className="multi-divider" style={{ left: `${position}%` }}><i>↔</i></div>
        </div>

        <div className="multi-slider-row">
          <span>{left.targetYear}</span>
          <input type="range" min="0" max="100" value={position} onChange={(event) => setPosition(Number(event.target.value))} aria-label="สัดส่วนเปรียบเทียบภาพ" />
          <span>{right.label}</span>
        </div>

        <div className="year-strip" aria-label="เลือกปีภาพย้อนหลัง">
          {catalog.leftChoices.map((item) => (
            <button type="button" key={item.id} className={item.id === leftId ? 'active' : ''} onClick={() => setLeftId(item.id)}>
              <strong>{item.targetYear}</strong>
              <small>{item.sensor}</small>
            </button>
          ))}
        </div>
      </section>

      <div className="legacy-drone-body">
        <DroneBaselinePage />
      </div>
    </div>
  )
}
