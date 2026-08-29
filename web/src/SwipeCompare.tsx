import { useRef, useState } from 'react'
import MapPane, { type LayerVisibility } from './MapPane'
import type { Epoch, TransectSelection, ViewState } from './types'

type Props = {
  before: Epoch
  after: Epoch
  layers: LayerVisibility
  opacity: number
  sharedView: ViewState
  onView: (value: ViewState) => void
  onTransect: (selection: TransectSelection) => void
}

const clamp = (value: number) => Math.min(100, Math.max(0, value))

export default function SwipeCompare({ before, after, layers, opacity, sharedView, onView, onTransect }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const [position, setPosition] = useState(50)

  const updateFromPointer = (clientX: number) => {
    const bounds = container.current?.getBoundingClientRect()
    if (!bounds || bounds.width === 0) return
    setPosition(clamp(((clientX - bounds.left) / bounds.width) * 100))
  }

  return (
    <div ref={container} className="swipe-compare">
      <div className="swipe-layer swipe-before">
        <MapPane
          epoch={before}
          label="BEFORE · ภาพก่อน"
          layers={layers}
          opacity={opacity}
          sharedView={sharedView}
          onView={onView}
          onTransect={onTransect}
          showControls={false}
        />
      </div>
      <div className="swipe-layer swipe-after" style={{ clipPath: `inset(0 0 0 ${position}%)` }}>
        <MapPane
          epoch={after}
          label="AFTER · ภาพหลัง"
          layers={layers}
          opacity={opacity}
          sharedView={sharedView}
          onView={onView}
          onTransect={onTransect}
          interactive={false}
          labelSide="right"
        />
      </div>

      <div
        className="swipe-divider"
        style={{ left: `${position}%` }}
        role="slider"
        tabIndex={0}
        aria-label="เลื่อนเส้นเพื่อเปรียบเทียบภาพก่อนและหลัง"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(position)}
        aria-valuetext={`แสดงภาพก่อน ${Math.round(position)} เปอร์เซ็นต์`}
        onPointerDown={(event) => {
          event.currentTarget.setPointerCapture(event.pointerId)
          updateFromPointer(event.clientX)
        }}
        onPointerMove={(event) => {
          if (event.currentTarget.hasPointerCapture(event.pointerId)) updateFromPointer(event.clientX)
        }}
        onPointerUp={(event) => {
          if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
        }}
        onPointerCancel={(event) => {
          if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
        }}
        onKeyDown={(event) => {
          if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
          event.preventDefault()
          if (event.key === 'ArrowLeft') setPosition((current) => clamp(current - 2))
          if (event.key === 'ArrowRight') setPosition((current) => clamp(current + 2))
          if (event.key === 'Home') setPosition(0)
          if (event.key === 'End') setPosition(100)
        }}
      >
        <span aria-hidden="true">↔</span>
      </div>

      <label className="swipe-range-control">
        <span>ก่อน {before.targetYear}</span>
        <input
          aria-label="สัดส่วนภาพก่อนและหลัง"
          type="range"
          min="0"
          max="100"
          value={position}
          onChange={(event) => setPosition(Number(event.target.value))}
        />
        <span>หลัง {after.targetYear}</span>
      </label>
    </div>
  )
}
