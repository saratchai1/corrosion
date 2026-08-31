import { useLayoutEffect, useRef } from 'react'
import MapPane from './MapPane'
import type { Epoch, LayerVisibility, TransectSelection, ViewState } from './types'

type Props = {
  epochs: Epoch[]
  beforeIndex: number
  afterIndex: number
  before: Epoch
  after: Epoch
  layers: LayerVisibility
  opacity: number
  sharedView: ViewState
  onView: (value: ViewState) => void
  onTransect: (value: TransectSelection) => void
  onBeforeChange: (value: number) => void
  onAfterChange: (value: number) => void
}

const clamp = (value: number) => Math.min(100, Math.max(0, value))

export default function SwipeCompare(props: Props) {
  const { epochs, beforeIndex, afterIndex, before, after, layers, opacity, sharedView, onView, onTransect, onBeforeChange, onAfterChange } = props
  const container = useRef<HTMLDivElement>(null)
  const afterLayer = useRef<HTMLDivElement>(null)
  const divider = useRef<HTMLDivElement>(null)
  const position = useRef(50)

  const paint = (value: number) => {
    const next = clamp(value)
    const width = container.current?.clientWidth ?? 0
    const height = container.current?.clientHeight ?? 0
    const x = width * next / 100
    position.current = next
    if (afterLayer.current) afterLayer.current.style.clip = `rect(0px, ${width}px, ${height}px, ${x}px)`
    if (divider.current) {
      divider.current.style.left = `${next}%`
      divider.current.setAttribute('aria-valuenow', String(Math.round(next)))
    }
  }

  useLayoutEffect(() => {
    const el = container.current
    if (!el) return
    const observer = new ResizeObserver(() => paint(position.current))
    observer.observe(el)
    paint(position.current)
    return () => observer.disconnect()
  }, [])

  const pointer = (clientX: number) => {
    const bounds = container.current?.getBoundingClientRect()
    if (!bounds) return
    paint(((clientX - bounds.left) / bounds.width) * 100)
  }

  return <div ref={container} className="swipe-compare">
    <div className="swipe-layer">
      <MapPane epoch={before} label="ก่อน / BEFORE" layers={layers} opacity={opacity} sharedView={sharedView} onView={onView} onTransect={onTransect} showControls={false} />
    </div>
    <div ref={afterLayer} className="swipe-layer swipe-after">
      <MapPane epoch={after} label="หลัง / AFTER" layers={layers} opacity={opacity} sharedView={sharedView} onView={onView} onTransect={onTransect} labelSide="right" />
    </div>

    <div className="swipe-toolbar">
      <label><span>ก่อน</span><select value={beforeIndex} onChange={(e) => onBeforeChange(Number(e.target.value))}>{epochs.map((e, i) => <option key={e.targetYear} value={i}>{e.targetYear}</option>)}</select></label>
      <div className="swipe-title"><strong>ลากเพื่อเทียบภาพ</strong><small>ก่อน ↔ หลัง</small></div>
      <label><span>หลัง</span><select value={afterIndex} onChange={(e) => onAfterChange(Number(e.target.value))}>{epochs.map((e, i) => <option key={e.targetYear} value={i}>{e.targetYear}</option>)}</select></label>
    </div>

    <div
      ref={divider}
      className="swipe-divider"
      role="slider"
      tabIndex={0}
      aria-label="สัดส่วนภาพก่อนและหลัง"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={50}
      onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); pointer(e.clientX) }}
      onPointerMove={(e) => { if (e.currentTarget.hasPointerCapture(e.pointerId)) pointer(e.clientX) }}
      onPointerUp={(e) => { if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId) }}
      onKeyDown={(e) => {
        if (e.key === 'ArrowLeft') paint(position.current - 2)
        if (e.key === 'ArrowRight') paint(position.current + 2)
        if (e.key === 'Home') paint(0)
        if (e.key === 'End') paint(100)
      }}
    ><span aria-hidden="true">↔</span></div>
  </div>
}
