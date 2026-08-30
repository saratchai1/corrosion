import { useEffect, useState } from 'react'
import PreplantingHistoryDashboard, {
  type PreplantingHistorySummary,
} from './PreplantingHistoryDashboard'
import TideAwareOverview from './TideAwareOverview'
import type { TideAwareSummary } from './types'

type Props = {
  summary: TideAwareSummary
  onOpenProject: () => void
  onOpenCoast: () => void
}

export default function TideAwareDashboard({ summary, onOpenProject, onOpenCoast }: Props) {
  const [view, setView] = useState<'history' | 'current'>('history')
  const [history, setHistory] = useState<PreplantingHistorySummary | null>(null)
  const [historyError, setHistoryError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    fetch('data/project_preplanting_history/summary.json')
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        return response.json()
      })
      .then((value: unknown) => {
        if (active) setHistory(value as PreplantingHistorySummary)
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
    <PreplantingHistoryDashboard
      history={history}
      onOpenCurrent={() => setView('current')}
      onOpenProject={onOpenProject}
      onOpenCoast={onOpenCoast}
    />
  )
}
