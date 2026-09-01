import { useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import DroneBaselinePage from './DroneBaselinePage'
import './drone-multiyear.css'

type ModeKey = 'rgb' | 'false_vegetation' | 'ndvi' | 'mndwi' | 'swir'
type VisualMap = Partial<Record<ModeKey, string>>

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
  visuals?: VisualMap
  spectralStatus?: string
  spectralDatesUsed?: string[]
}

type RightChoice = {
  id: string
  label: string
  asset: string
  note: string
  visuals?: VisualMap
  supportedModes?: ModeKey[]
  spectralStatus?: string
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
  rightChoices: RightChoice[]
  spectralModes?: Array<{ id: ModeKey; label: string; description: string }>
  visual_mode_guard?: string
}

type ThemeMode = 'ocean' | 'mangrove' | 'slate'

type ModeDefinition = {
  id: ModeKey
  label: string
  short: string
  note: string
  legend?: Array<{ label: string; color: string }>
}

const modeDefinitions: ModeDefinition[] = [
  { id: 'rgb', label: 'RGB', short: 'RGB', note: 'สีจริง Red–Green–Blue' },
  { id: 'false_vegetation', label: 'False Color', short: 'NIR–R–G', note: 'สีเทียม NIR–Red–Green · พืชเด่นเป็นสีแดง' },
  {
    id: 'ndvi',
    label: 'NDVI',
    short: '(NIR−R)/(NIR+R)',
    note: 'ความเขียวของพืชจาก NIR และ Red',
    legend: [
      { label: 'น้ำ / ต่ำ', color: '#1c3e73' },
      { label: 'ดิน / เบาบาง', color: '#daaF70' },
      { label: 'พืชปานกลาง', color: '#85b55d' },
      { label: 'พืชหนาแน่น', color: '#08452a' },
    ],
  },
  {
    id: 'mndwi',
    label: 'MNDWI',
    short: '(G−SWIR1)/(G+SWIR1)',
    note: 'เน้นน้ำ–แผ่นดินจาก Green และ SWIR1',
    legend: [
      { label: 'ดิน / พืช', color: '#6c4427' },
      { label: 'รอยต่อ', color: '#cac7b1' },
      { label: 'น้ำ', color: '#184fab' },
      { label: 'น้ำเด่น', color: '#082d68' },
    ],
  },
  { id: 'swir', label: 'SWIR', short: 'SWIR1–NIR–R', note: 'สีเทียม SWIR1–NIR–Red · ช่วยดูความชื้น ดินเปิด และน้ำ' },
]

const themes: Array<{ id: ThemeMode; label: string }> = [
  { id: 'ocean', label: 'Ocean' },
  { id: 'mangrove', label: 'Mangrove' },
  { id: 'slate', label: 'Slate' },
]

function imageFor(choice: { asset: string; visuals?: VisualMap }, mode: ModeKey) {
  return choice.visuals?.[mode] ?? (mode === 'rgb' ? choice.visuals?.rgb ?? choice.asset : null)
}

export default function DroneMultiYearPage() {
  const [catalog, setCatalog] = useState<CompareCatalog | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [leftId, setLeftId] = useState('')
  const [rightId, setRightId] = useState('')
  const [position, setPosition] = useState(50)
  const [mode, setMode] = useState<ModeKey>('rgb')
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
  const activeMode = modeDefinitions.find((item) => item.id === mode) ?? modeDefinitions[0]

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

  const leftImage = imageFor(left, mode)
  const rightSupportsMode = right.id !== 'drone' && Boolean(imageFor(right, mode))
  const rightMode: ModeKey = rightSupportsMode ? mode : 'rgb'
  const rightImage = imageFor(right, rightMode)
  const missingSpectralAsset = !leftImage || !rightImage
  const rightBadge = right.id === 'drone' && mode !== 'rgb' ? `${right.label} · RGB` : `${right.label} · ${modeDefinitions.find((item) => item.id === rightMode)?.label ?? 'RGB'}`

  return (
    <div className={`drone-multiyear-page compare-theme-${theme}`}>
      <section className="multi-compare-panel">
        <div className="multi-compare-head">
          <div>
            <span>SAME-EXTENT MULTI-YEAR · ACTUAL MULTISPECTRAL PRODUCTS</span>
            <h1>{left.label} ↔ {right.label}</h1>
          </div>
          <div className="multi-compare-meta">
            <strong>{catalog.width_px} × {catalog.height_px}px</strong>
            <small>ขอบเขตเดียวกันทุกปี · {activeMode.label}</small>
          </div>
        </div>

        <div className="multi-compare-controlbar spectral-controlbar">
          <label className="multi-control">
            <span>ด้านซ้าย · ย้อนหลัง</span>
            <select value={leftId} onChange={(event) => setLeftId(event.target.value)}>
              {catalog.leftChoices.map((item) => (
                <option key={item.id} value={item.id}>{item.label}</option>
              ))}
            </select>
            <small>{left.sensor} · ภาพจริง {left.actualYear} · {(left.spectralDatesUsed ?? left.dates).length} scenes</small>
          </label>

          <label className="multi-control">
            <span>ด้านขวา · ปัจจุบัน</span>
            <select value={rightId} onChange={(event) => setRightId(event.target.value)}>
              {catalog.rightChoices.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
            </select>
            <small>{right.id === 'drone' ? `${right.note} · RGB only` : right.note}</small>
          </label>

          <div className="multi-control visual-mode-control spectral-mode-control">
            <span>ผลิตภัณฑ์ดาวเทียม</span>
            <div className="mode-buttons spectral-mode-buttons">
              {modeDefinitions.map((item) => (
                <button type="button" key={item.id} className={mode === item.id ? 'active' : ''} onClick={() => setMode(item.id)}>
                  <strong>{item.label}</strong><small>{item.short}</small>
                </button>
              ))}
            </div>
            <small>{activeMode.note}</small>
          </div>

          <div className="multi-control theme-control">
            <span>สีหน้าเว็บ</span>
            <div className="theme-buttons">
              {themes.map((item) => (
                <button type="button" key={item.id} className={theme === item.id ? 'active' : ''} onClick={() => setTheme(item.id)}>{item.label}</button>
              ))}
            </div>
            <small>เปลี่ยนเฉพาะ UI ไม่เปลี่ยนข้อมูล spectral</small>
          </div>
        </div>

        <div className="spectral-note-row">
          <div><strong>{activeMode.label}</strong><span>{activeMode.note}</span></div>
          {right.id === 'drone' && mode !== 'rgb' ? <p>ด้านซ้าย = {activeMode.label} จาก band ดาวเทียมจริง · ด้านขวา = Drone HR แบบ RGB เพราะโดรนชุดนี้ไม่มี NIR/SWIR</p> : <p>ทั้งสองฝั่งใช้โหมด {activeMode.label} จาก band ดาวเทียมจริง</p>}
        </div>

        {missingSpectralAsset ? (
          <div className="spectral-missing"><strong>spectral asset ยังไม่พร้อม</strong><span>รอ pipeline สร้าง {activeMode.label} ของปี {left.targetYear}</span></div>
        ) : (
          <div
            ref={stageRef}
            className={`multi-compare-stage ${dragging ? 'dragging' : ''}`}
            style={{ aspectRatio: `${catalog.width_px}/${catalog.height_px}` }}
            onPointerDown={pointerDown}
            onPointerMove={pointerMove}
            onPointerUp={pointerUp}
            onPointerCancel={pointerUp}
          >
            <img className="multi-image base" src={leftImage} alt={`${left.label} ${activeMode.label}`} draggable={false} />
            <div className="multi-image-overlay" style={{ clipPath: `inset(0 0 0 ${position}%)` }}>
              <img className="multi-image" src={rightImage} alt={rightBadge} draggable={false} />
            </div>
            <span className="multi-badge left">{left.label} · {activeMode.label}</span>
            <span className="multi-badge right">{rightBadge}</span>
            <div className="multi-divider" style={{ left: `${position}%` }}><i>↔</i></div>
          </div>
        )}

        <div className="multi-slider-row">
          <span>{left.targetYear} · {activeMode.label}</span>
          <input type="range" min="0" max="100" value={position} onChange={(event) => setPosition(Number(event.target.value))} aria-label="สัดส่วนเปรียบเทียบภาพ" />
          <span>{rightBadge}</span>
        </div>

        {activeMode.legend ? (
          <div className={`spectral-legend spectral-legend-${mode}`}>
            <strong>{activeMode.label}</strong>
            <div>{activeMode.legend.map((item) => <span key={item.label}><i style={{ background: item.color }} />{item.label}</span>)}</div>
          </div>
        ) : null}

        <div className="year-strip" aria-label="เลือกปีภาพย้อนหลัง">
          {catalog.leftChoices.map((item) => (
            <button type="button" key={item.id} className={item.id === leftId ? 'active' : ''} onClick={() => setLeftId(item.id)}>
              <strong>{item.targetYear}</strong>
              <small>{item.sensor}</small>
            </button>
          ))}
        </div>

        <p className="spectral-science-guard">{catalog.visual_mode_guard ?? 'Spectral modes are produced from actual multispectral bands; Drone HR remains RGB-only.'}</p>
      </section>

      <div className="legacy-drone-body">
        <DroneBaselinePage />
      </div>
    </div>
  )
}
