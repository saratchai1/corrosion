import { useEffect, useState } from 'react'
import PlantingEvidenceInjector, {
  type PlantingAwareSummary,
} from './PlantingEvidenceInjector'
import PlotOverlayInjector from './PlotOverlayInjector'
import PreplantingHistoryDashboardV2, {
  type PreplantingHistorySummaryV2,
} from './PreplantingHistoryDashboardV2'
import TideAwareOverview from './TideAwareOverview'
import type { TideAwareSummary } from './types'

type Props = {
  summary: TideAwareSummary
  onOpenProject: () => void
  onOpenCoast: () => void
}

export default function TideAwareDashboard({ summary, onOpenProject, onOpenCoast }: Props) {
  const [view, setView] = useState<'history' | 'current'>('history')
  const [history, setHistory] = useState<PreplantingHistorySummaryV2 | null>(null)
  const [historyError, setHistoryError] = useState<string | null>(null)
  const [planting, setPlanting] = useState<PlantingAwareSummary | null>(null)

  useEffect(() => {
    const handleInternalAnchorClick = (event: MouseEvent) => {
      const source = event.target
      if (!(source instanceof Element)) return

      const anchor = source.closest<HTMLAnchorElement>('a[href^="#"]')
      const href = anchor?.getAttribute('href')
      if (!href || href === '#') return

      const target = document.getElementById(decodeURIComponent(href.slice(1)))
      if (!target) return

      event.preventDefault()
      target.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }

    document.addEventListener('click', handleInternalAnchorClick)
    return () => document.removeEventListener('click', handleInternalAnchorClick)
  }, [])

  useEffect(() => {
    let active = true
    fetch('data/project_preplanting_history/summary.json')
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        return response.json()
      })
      .then((value: unknown) => {
        if (active) setHistory(value as PreplantingHistorySummaryV2)
      })
      .catch((reason: unknown) => {
        if (active) {
          setHistoryError(reason instanceof Error ? reason.message : String(reason))
          setView('current')
        }
      })
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    let active = true
    fetch('data/project_planting_aware/summary.json')
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        return response.json()
      })
      .then((value: unknown) => {
        if (active) setPlanting(value as PlantingAwareSummary)
      })
      .catch(() => {
        if (active) setPlanting(null)
      })
    return () => {
      active = false
    }
  }, [])

  if (view === 'current') {
    return (
      <>
        <div className="history-current-return">
          <button type="button" onClick={() => setView('history')} disabled={!history}>
            ← กลับไปดูว่า ก่อนปี 2023 เคยมีสัญญาณกัดเซาะหรือไม่
          </button>
          {historyError && <span className="history-load-note">โหลดข้อมูลย้อนหลังไม่ได้: {historyError}</span>}
        </div>
        <TideAwareOverview
          summary={summary}
          onOpenProject={onOpenProject}
          onOpenCoast={onOpenCoast}
        />
      </>
    )
  }

  if (!history) {
    return <main className="history-loading">กำลังเปิดภาพและผลวิเคราะห์ย้อนหลัง 2017–2026…</main>
  }

  return (
    <>
      <PreplantingHistoryDashboardV2
        history={history}
        onOpenCurrent={() => setView('current')}
        onOpenProject={onOpenProject}
        onOpenCoast={onOpenCoast}
      />
      {planting && <PlantingEvidenceInjector summary={planting} />}
      <PlotOverlayInjector scenes={history.scene_selection.display_scenes} />
    </>
  )
}
