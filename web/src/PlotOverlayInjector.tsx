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
    zoomReset.setAttribute('aria-label', 'รีเซ็ตการซูมเป็น 100 เปอร์เซ็นต์')

    const zoomIn = document.createElement('button')
    zoomIn.type = 'button'
    zoomIn.className = 'spectral-zoom-button'
    zoomIn.textContent = '+'
    zoomIn.setAttribute('aria-label', 'ซูมเข้า')

    zoomControls.append(zoomOut, zoomReset, zoomIn)
    stage.append(zoomControls)

    let visible = true
    let zoom = 1

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

    const renderZoom = () => {
      const transform = `scale(${zoom.toFixed(2)})`
      beforeLayer.style.transform = transform
      afterLayer.style.transform = transform
      zoomReset.textContent = `${Math.round(zoom * 100)}%`
      zoomOut.disabled = zoom <= MIN_ZOOM + 0.001
      zoomIn.disabled = zoom >= MAX_ZOOM - 0.001
    }

    const setZoom = (next: number) => {
      zoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, Math.round(next * 4) / 4))
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
      setZoom(1)
    })

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
    }
  }, [scenes])

  return null
}
