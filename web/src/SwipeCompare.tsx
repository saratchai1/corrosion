import { useLayoutEffect, useRef } from 'react'
import MapPane, { type LayerVisibility } from './MapPane'
import type { Epoch, TransectSelection, ViewState } from './types'

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
  onTransect: (selection: TransectSelection) => void
  onBeforeChange: (value: number) => void
  onAfterChange: (value: number) => void
}

const clamp = (value: number) => Math.min(100, Math.max(0, value))
const clampZoom = (value: number) => Math.min(18, Math.max(8, value))

export default function SwipeCompare({ epochs, beforeIndex, afterIndex, before, after, layers, opacity, sharedView, onView, onTransect, onBeforeChange, onAfterChange }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const afterLayer = useRef<HTMLDivElement>(null)
  const divider = useRef<HTMLDivElement>(null)
  const range = useRef<HTMLInputElement>(null)
  const geometry = useRef({ width: 0, height: 0, left: 0 })
  const position = useRef(50)
  const pendingPosition = useRef<number | null>(null)
  const frame = useRef<number | null>(null)

  const paintPosition = (value: number) => {
    const next = clamp(value)
    const { width, height } = geometry.current
    const x = (next / 100) * width
    position.current = next
    if (afterLayer.current) afterLayer.current.style.clip = `rect(0px, ${width}px, ${height}px, ${x}px)`
    if (divider.current) {
      divider.current.style.transform = `translate3d(${x}px, 0, 0) translateX(-50%)`
      divider.current.setAttribute('aria-valuenow', String(Math.round(next)))
      divider.current.setAttribute('aria-valuetext', `แสดงภาพก่อน ${Math.round(next)} เปอร์เซ็นต์`)
    }
    if (range.current) range.current.value = String(next)
  }

  useLayoutEffect(() => {
    const element = container.current
    if (!element) return
    const measure = () => {
      const bounds = element.getBoundingClientRect()
      geometry.current = { width: bounds.width, height: bounds.height, left: bounds.left }
      paintPosition(position.current)
    }
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(element)
    return () => {
      observer.disconnect()
      if (frame.current !== null) cancelAnimationFrame(frame.current)
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const schedulePosition = (value: number) => {
    pendingPosition.current = clamp(value)
    if (frame.current !== null) return
    frame.current = requestAnimationFrame(() => {
      if (pendingPosition.current !== null) paintPosition(pendingPosition.current)
      pendingPosition.current = null
      frame.current = null
    })
  }

  const updateFromPointer = (clientX: number) => {
    const { left, width } = geometry.current
    if (width === 0) return
    schedulePosition(((clientX - left) / width) * 100)
  }

  const updateZoom = (delta: number) => onView({ ...sharedView, zoom: clampZoom(sharedView.zoom + delta) })

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
      <div ref={afterLayer} className="swipe-layer swipe-after">
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

      <div className="swipe-toolbar" aria-label="ตัวควบคุมแผนที่เปรียบเทียบ">
        <label>
          <span>ก่อน / Before</span>
          <select aria-label="เลือกภาพก่อน" value={beforeIndex} onChange={(event) => onBeforeChange(Number(event.target.value))}>
            {epochs.map((item, itemIndex) => <option value={itemIndex} key={item.targetYear}>{item.targetYear} · {item.actualYear}</option>)}
          </select>
        </label>
        <div className="swipe-zoom-control">
          <span>ZOOM {sharedView.zoom.toFixed(1)}</span>
          <div>
            <button type="button" aria-label="ลดการซูม" onClick={() => updateZoom(-1)}>−</button>
            <button type="button" aria-label="ขยายแผนที่" onClick={() => updateZoom(1)}>+</button>
          </div>
        </div>
        <label>
          <span>หลัง / After</span>
          <select aria-label="เลือกภาพหลัง" value={afterIndex} onChange={(event) => onAfterChange(Number(event.target.value))}>
            {epochs.map((item, itemIndex) => <option value={itemIndex} key={item.targetYear}>{item.targetYear} · {item.actualYear}</option>)}
          </select>
        </label>
      </div>

      <div
        ref={divider}
        className="swipe-divider"
        role="slider"
        tabIndex={0}
        aria-label="เลื่อนเส้นเพื่อเปรียบเทียบภาพก่อนและหลัง"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={50}
        aria-valuetext="แสดงภาพก่อน 50 เปอร์เซ็นต์"
        onPointerDown={(event) => {
          const bounds = container.current?.getBoundingClientRect()
          if (bounds) geometry.current = { width: bounds.width, height: bounds.height, left: bounds.left }
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
          const currentPosition = pendingPosition.current ?? position.current
          if (event.key === 'ArrowLeft') schedulePosition(currentPosition - 2)
          if (event.key === 'ArrowRight') schedulePosition(currentPosition + 2)
          if (event.key === 'Home') schedulePosition(0)
          if (event.key === 'End') schedulePosition(100)
        }}
      >
        <span aria-hidden="true">↔</span>
      </div>

      <label className="swipe-range-control">
        <span>ก่อน {before.targetYear}</span>
        <input
          ref={range}
          aria-label="สัดส่วนภาพก่อนและหลัง"
          type="range"
          min="0"
          max="100"
          defaultValue="50"
          onInput={(event) => schedulePosition(Number(event.currentTarget.value))}
        />
        <span>หลัง {after.targetYear}</span>
      </label>
    </div>
  )
}
