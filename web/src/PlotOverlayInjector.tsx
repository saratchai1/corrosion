import { useEffect } from 'react'
import './plotOverlay.css'

type OverlayScene = {
  year: number
  plot_overlays?: Record<string, string>
}

type Props = {
  scenes: OverlayScene[]
}

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

    stage.append(afterOverlay, beforeOverlay)

    const viewTabs = compare.querySelector<HTMLElement>('.spectral-view-tabs')
    const toggle = document.createElement('button')
    toggle.type = 'button'
    toggle.className = 'spectral-overlay-toggle active'
    toggle.innerHTML = '<strong>กรอบแปลง: เปิด</strong><small>SVG overlay ในเว็บ</small>'
    viewTabs?.append(toggle)

    let visible = true

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
      beforeOverlay.style.clipPath = `inset(0 ${100 - split}% 0 0)`
    }

    const updateSources = () => {
      const years = getYears()
      const view = getView()
      beforeOverlay.src = overlayPath(scenes, years.before, view)
      afterOverlay.src = overlayPath(scenes, years.after, view)
      updateClip()
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

    toggle.addEventListener('click', (event) => {
      event.preventDefault()
      event.stopPropagation()
      setVisibility(!visible)
    })

    const scheduleUpdate = () => window.setTimeout(updateSources, 0)
    compare.addEventListener('change', scheduleUpdate)
    compare.addEventListener('click', scheduleUpdate)

    const divider = compare.querySelector<HTMLElement>('.spectral-divider')
    const observer = new MutationObserver(updateClip)
    if (divider) observer.observe(divider, { attributes: true, attributeFilter: ['style'] })

    updateSources()

    return () => {
      observer.disconnect()
      compare.removeEventListener('change', scheduleUpdate)
      compare.removeEventListener('click', scheduleUpdate)
      beforeOverlay.remove()
      afterOverlay.remove()
      toggle.remove()
    }
  }, [scenes])

  return null
}
