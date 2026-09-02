import { useEffect, useMemo, useRef, useState } from 'react'
import './superres25.css'

type Location = {
  id: string
  label: string
  lon: number
  lat: number
  scene_id: string
  date: string
  original: string
  superres: string
}

type Summary = {
  scene_id: string
  date: string
  locations: Location[]
}

export default function SuperResolutionPage() {
  const [summary, setSummary] = useState<Summary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [activeId, setActiveId] = useState('91-stc')
  const [split, setSplit] = useState(50)
  const [zoom, setZoom] = useState(1)
  const frameRef = useRef<HTMLDivElement | null>(null)
  const dragging = useRef(false)

  useEffect(() => {
    fetch('data/superres25/summary.json', { cache: 'no-store' })
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        return response.json()
      })
      .then((value: Summary) => setSummary(value))
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : String(reason)))
  }, [])

  const active = useMemo(
    () => summary?.locations.find((item) => item.id === activeId) ?? summary?.locations[0] ?? null,
    [summary, activeId],
  )

  const updateSplit = (clientX: number) => {
    const frame = frameRef.current
    if (!frame) return
    const rect = frame.getBoundingClientRect()
    const value = ((clientX - rect.left) / rect.width) * 100
    setSplit(Math.max(4, Math.min(96, value)))
  }

  if (error) {
    return <main className="sr25-status">โหลดภาพไม่สำเร็จ · {error}</main>
  }

  if (!summary || !active) {
    return <main className="sr25-status">กำลังเปิดภาพ…</main>
  }

  return (
    <main className="sr25-shell">
      <header className="sr25-topbar">
        <div className="sr25-brand">
          <span>สมุทรสงคราม</span>
          <strong>SENTINEL-2</strong>
        </div>
        <div className="sr25-meta">
          <span>{active.label}</span>
          <span>{active.date}</span>
        </div>
      </header>

      <section className="sr25-stage-wrap">
        <div
          ref={frameRef}
          className="sr25-frame"
          onPointerDown={(event) => {
            dragging.current = true
            event.currentTarget.setPointerCapture(event.pointerId)
            updateSplit(event.clientX)
          }}
          onPointerMove={(event) => {
            if (dragging.current) updateSplit(event.clientX)
          }}
          onPointerUp={(event) => {
            dragging.current = false
            event.currentTarget.releasePointerCapture(event.pointerId)
          }}
          onPointerCancel={() => { dragging.current = false }}
        >
          <div className="sr25-image-plane" style={{ transform: `scale(${zoom})` }}>
            <img className="sr25-image sr25-original" src={active.original} alt="10 m" draggable={false} />
            <div className="sr25-sr-clip" style={{ clipPath: `inset(0 ${100 - split}% 0 0)` }}>
              <img className="sr25-image" src={active.superres} alt="2.5 m" draggable={false} />
            </div>
          </div>

          <div className="sr25-side-label sr25-left-label">2.5 m</div>
          <div className="sr25-side-label sr25-right-label">10 m</div>
          <div className="sr25-divider" style={{ left: `${split}%` }}>
            <span />
          </div>
        </div>
      </section>

      <footer className="sr25-controls">
        <div className="sr25-locations">
          {summary.locations.map((item) => (
            <button
              key={item.id}
              className={item.id === active.id ? 'active' : ''}
              onClick={() => {
                setActiveId(item.id)
                setSplit(50)
                setZoom(1)
              }}
            >
              {item.label}
            </button>
          ))}
        </div>

        <label className="sr25-zoom">
          <span>{zoom.toFixed(1)}×</span>
          <input
            aria-label="Zoom"
            type="range"
            min="1"
            max="4"
            step="0.1"
            value={zoom}
            onChange={(event) => setZoom(Number(event.target.value))}
          />
        </label>
      </footer>
    </main>
  )
}
