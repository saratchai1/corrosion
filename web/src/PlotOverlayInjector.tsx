import { useEffect } from 'react'
import './plotOverlay.css'

type OverlayScene = {
  year: number
  plot_overlays?: Record<string, string>
}

type Props = {
  scenes: OverlayScene[]
}

const MIN_ZOOM = 1
const MAX_ZOOM = 3
const ZOOM_STEP = 0.25

function overlayPath(scenes: OverlayScene[], year: number, view: 'focus' | 'full') {
  const scene = scenes.find((item) => item.year === year)
  return scene?.plot_overlays?.[view]
    ?? `data/project_preplanting_history/visuals/${view}/overlay/${year}.svg`
}

export default function PlotOverlayInjector({ scenes }: Props) {
  useEffect(() => {
    const stage = document.querySelector<HTMLDivElement>('.spectral-swipe-stage')
    const compare = stage?.closest<HTMLElement>('.spectral-compare')
    if (!stage || !compare) return

    const existingImages = Array.from(stage.querySelectorAll<HTMLImageElement>(':scope > img'))
    const beforeRaster = existingImages.find((image) => image.classList.contains('before'))
    const afterRaster = existingImages.find((image) => !image.classList.contains('before'))
    if (!beforeRaster || !afterRaster) return

    const originalBeforeClip = beforeRaster.style.clipPath

    const afterLayer = document.createElement('div')
    afterLayer.className = 'spectral-zoom-layer spectral-zoom-layer-after'

    const beforeClip = document.createElement('div')
    beforeClip.className = 'spectral-before-clip'

    const beforeLayer = document.createElement('div')
    beforeLayer.className = 'spectral-zoom-layer spectral-zoom-layer-before'

    beforeRaster.style.clipPath = 'none'
    afterLayer.append(afterRaster)
    beforeLayer.append(beforeRaster)
    beforeClip.append(beforeLayer)
    stage.prepend(beforeClip)
    stage.prepend(afterLayer)

    const afterOverlay = document.createElement('img')
    afterOverlay.className = 'spectral-web-map-overlay spectral-web-map-overlay-after'
    afterOverlay.alt = ''
    afterOverlay.setAttribute('aria-hidden', 'true')
    afterOverlay.draggable = false

    const beforeOverlay = document.createElement('img')
    beforeOverlay.className = 'spectral-web-map-overlay spectral-web-map-overlay-before'
    beforeOverlay.alt = ''
    beforeOverlay.setAttribute('aria-hidden', 'true')
    beforeOverlay.draggable = false

    afterLayer.append(afterOverlay)
    beforeLayer.append(beforeOverlay)

    const viewTabs = compare.querySelector<HTMLElement>('.spectral-view-tabs')
    const toggle = document.createElement('button')
    toggle.type = 'button'
    toggle.className = 'spectral-overlay-toggle active'
    toggle.innerHTML = '<strong>กรอบแปลง: เปิด</strong><small>SVG overlay ในเว็บ</small>'
    viewTabs?.append(toggle)

    const zoomControls = document.createElement('div')
    zoomControls.className = 'spectral-zoom-controls'
    zoomControls.setAttribute('aria-label', 'ควบคุมการซูมภาพดาวเทียม')

    const zoomOut = document.createElement('button')
    zoomOut.type = 'button'
    zoomOut.className = 'spectral-zoom-button'
    zoomOut.textContent = '−'
    zoomOut.setAttribute('aria-label', 'ซูมออก')

    const zoomReset = document.createElement('button')
    zoomReset.type = 'button'
    zoomReset.className = 'spectral-zoom-reset'
    zoomReset.setAttribute('aria-label', 'รีเซ็ตการซูมและตำแหน่งภาพ')
    zoomReset.title = 'กลับ 100% และกึ่งกลางภาพ'

    const zoomIn = document.createElement('button')
    zoomIn.type = 'button'
    zoomIn.className = 'spectral-zoom-button'
    zoomIn.textContent = '+'
    zoomIn.setAttribute('aria-label', 'ซูมเข้า')

    zoomControls.append(zoomOut, zoomReset, zoomIn)
    stage.append(zoomControls)

    const panHint = document.createElement('div')
    panHint.className = 'spectral-pan-hint'
    panHint.setAttribute('aria-live', 'polite')
    stage.append(panHint)

    let visible = true
    let zoom = 1
    let panX = 0
    let panY = 0
    let panning = false
    let panPointerId: number | null = null
    let panStartClientX = 0
    let panStartClientY = 0
    let panStartX = 0
    let panStartY = 0

    const getView = (): 'focus' | 'full' => {
      const buttons = Array.from(compare.querySelectorAll<HTMLButtonElement>('.spectral-view-tabs > button:not(.spectral-overlay-toggle)'))
      const active = buttons.find((button) => button.classList.contains('active'))
      return active === buttons[1] ? 'full' : 'focus'
    }

    const getYears = () => {
      const selects = Array.from(compare.querySelectorAll<HTMLSelectElement>('.spectral-controls select'))
      return {
        before: Number(selects[0]?.value || 2020),
        after: Number(selects[selects.length - 1]?.value || 2026),
      }
    }

    const updateClip = () => {
      const divider = compare.querySelector<HTMLElement>('.spectral-divider')
      const split = Number.parseFloat(divider?.style.left || '50')
      beforeClip.style.clipPath = `inset(0 ${100 - split}% 0 0)`
    }

    const updateSources = () => {
      const years = getYears()
      const view = getView()
      beforeOverlay.src = overlayPath(scenes, years.before, view)
      afterOverlay.src = overlayPath(scenes, years.after, view)
      updateClip()
    }

    const clampPan = (nextX: number, nextY: number) => {
      if (zoom <= MIN_ZOOM + 0.001) return { x: 0, y: 0 }
      const bounds = stage.getBoundingClientRect()
      const maxX = Math.max(0, (bounds.width * (zoom - 1)) / 2)
      const maxY = Math.max(0, (bounds.height * (zoom - 1)) / 2)
      return {
        x: Math.max(-maxX, Math.min(maxX, nextX)),
        y: Math.max(-maxY, Math.min(maxY, nextY)),
      }
    }

    const renderTransform = () => {
      const clamped = clampPan(panX, panY)
      panX = clamped.x
      panY = clamped.y
      const transform = `translate3d(${panX.toFixed(1)}px, ${panY.toFixed(1)}px, 0) scale(${zoom.toFixed(2)})`
      beforeLayer.style.transform = transform
      afterLayer.style.transform = transform
      stage.classList.toggle('spectral-can-pan', zoom > MIN_ZOOM + 0.001)
      stage.classList.toggle('spectral-is-panning', panning)
      panHint.textContent = zoom > MIN_ZOOM + 0.001
        ? 'ลากพื้นภาพเพื่อเลื่อน ซ้าย–ขวา–บน–ล่าง · ลากเส้น ↔ เพื่อเทียบ Before/After'
        : 'กด + เพื่อซูม แล้วลากพื้นภาพเพื่อเลื่อนตำแหน่ง'
    }

    const renderZoom = () => {
      renderTransform()
      zoomReset.textContent = `${Math.round(zoom * 100)}%`
      zoomOut.disabled = zoom <= MIN_ZOOM + 0.001
      zoomIn.disabled = zoom >= MAX_ZOOM - 0.001
    }

    const setZoom = (next: number) => {
      zoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, Math.round(next * 4) / 4))
      if (zoom <= MIN_ZOOM + 0.001) {
        panX = 0
        panY = 0
      }
      renderZoom()
    }

    const resetView = () => {
      zoom = 1
      panX = 0
      panY = 0
      renderZoom()
    }

    const setVisibility = (next: boolean) => {
      visible = next
      beforeOverlay.hidden = !visible
      afterOverlay.hidden = !visible
      toggle.classList.toggle('active', visible)
      toggle.innerHTML = visible
        ? '<strong>กรอบแปลง: เปิด</strong><small>SVG overlay ในเว็บ</small>'
        : '<strong>กรอบแปลง: ปิด</strong><small>คลิกเพื่อแสดงอีกครั้ง</small>'
    }

    const stopSliderEvent = (event: Event) => {
      event.stopPropagation()
    }

    for (const type of ['pointerdown', 'pointermove', 'pointerup', 'click'] as const) {
      zoomControls.addEventListener(type, stopSliderEvent)
    }

    toggle.addEventListener('click', (event) => {
      event.preventDefault()
      event.stopPropagation()
      setVisibility(!visible)
    })

    zoomOut.addEventListener('click', (event) => {
      event.preventDefault()
      setZoom(zoom - ZOOM_STEP)
    })
    zoomIn.addEventListener('click', (event) => {
      event.preventDefault()
      setZoom(zoom + ZOOM_STEP)
    })
    zoomReset.addEventListener('click', (event) => {
      event.preventDefault()
      resetView()
    })

    const isInteractiveTarget = (target: EventTarget | null) => {
      if (!(target instanceof Element)) return false
      return Boolean(target.closest(
        '.spectral-divider, .spectral-zoom-controls, .spectral-year-label, .spectral-location-note, .spectral-pan-hint',
      ))
    }

    const onPanPointerDown = (event: PointerEvent) => {
      if (zoom <= MIN_ZOOM + 0.001 || isInteractiveTarget(event.target)) return
      if (event.button !== 0 && event.pointerType === 'mouse') return

      panning = true
      panPointerId = event.pointerId
      panStartClientX = event.clientX
      panStartClientY = event.clientY
      panStartX = panX
      panStartY = panY
      stage.setPointerCapture(event.pointerId)
      renderTransform()
      event.preventDefault()
      event.stopPropagation()
    }

    const onPanPointerMove = (event: PointerEvent) => {
      if (!panning || event.pointerId !== panPointerId) return
      const next = clampPan(
        panStartX + (event.clientX - panStartClientX),
        panStartY + (event.clientY - panStartClientY),
      )
      panX = next.x
      panY = next.y
      renderTransform()
      event.preventDefault()
      event.stopPropagation()
    }

    const endPan = (event: PointerEvent) => {
      if (!panning || event.pointerId !== panPointerId) return
      panning = false
      panPointerId = null
      if (stage.hasPointerCapture(event.pointerId)) stage.releasePointerCapture(event.pointerId)
      renderTransform()
      event.preventDefault()
      event.stopPropagation()
    }

    stage.addEventListener('pointerdown', onPanPointerDown, true)
    stage.addEventListener('pointermove', onPanPointerMove, true)
    stage.addEventListener('pointerup', endPan, true)
    stage.addEventListener('pointercancel', endPan, true)

    const onResize = () => renderTransform()
    window.addEventListener('resize', onResize)

    const scheduleUpdate = () => window.setTimeout(updateSources, 0)
    compare.addEventListener('change', scheduleUpdate)
    compare.addEventListener('click', scheduleUpdate)

    const divider = compare.querySelector<HTMLElement>('.spectral-divider')
    const observer = new MutationObserver(updateClip)
    if (divider) observer.observe(divider, { attributes: true, attributeFilter: ['style'] })

    updateSources()
    renderZoom()

    return () => {
      observer.disconnect()
      compare.removeEventListener('change', scheduleUpdate)
      compare.removeEventListener('click', scheduleUpdate)
      window.removeEventListener('resize', onResize)
      stage.removeEventListener('pointerdown', onPanPointerDown, true)
      stage.removeEventListener('pointermove', onPanPointerMove, true)
      stage.removeEventListener('pointerup', endPan, true)
      stage.removeEventListener('pointercancel', endPan, true)
      stage.classList.remove('spectral-can-pan', 'spectral-is-panning')
      for (const type of ['pointerdown', 'pointermove', 'pointerup', 'click'] as const) {
        zoomControls.removeEventListener(type, stopSliderEvent)
      }
      beforeRaster.style.clipPath = originalBeforeClip
      stage.prepend(beforeRaster)
      stage.prepend(afterRaster)
      afterLayer.remove()
      beforeClip.remove()
      toggle.remove()
      zoomControls.remove()
      panHint.remove()
    }
  }, [scenes])

  return null
}
