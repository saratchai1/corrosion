import { useEffect, useState } from 'react'
import CurrentEvidencePage from './CurrentEvidencePage'
import DroneMultiYearPage from './DroneMultiYearPage'
import HistoryPage from './HistoryPage'
import MapExplorerPage from './MapExplorerPage'
import PrimaryNav, { type SiteRoute } from './PrimaryNav'
import ReportPage from './ReportPage'
import type { DataIndex, EvidenceManifest, ExecutiveSummary } from './types'

const DATA = 'data/surat_thani/'

function routeFromHash(): SiteRoute {
  const value = window.location.hash.replace(/^#/, '')
  if (value === 'current' || value === 'drone' || value === 'report' || value === 'map') return value
  return 'history'
}

export default function App() {
  const [route, setRoute] = useState<SiteRoute>(routeFromHash)
  const [index, setIndex] = useState<DataIndex | null>(null)
  const [exec, setExec] = useState<ExecutiveSummary | null>(null)
  const [manifest, setManifest] = useState<EvidenceManifest | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const onHash = () => setRoute(routeFromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  useEffect(() => {
    Promise.all([
      fetch(`${DATA}index.json`).then((response) => {
        if (!response.ok) throw new Error(`index.json HTTP ${response.status}`)
        return response.json()
      }),
      fetch(`${DATA}executive_summary.json`).then((response) => {
        if (!response.ok) throw new Error(`executive_summary.json HTTP ${response.status}`)
        return response.json()
      }),
      fetch(`${DATA}evidence_manifest.json`).then((response) => {
        if (!response.ok) throw new Error(`evidence_manifest.json HTTP ${response.status}`)
        return response.json()
      }),
    ])
      .then(([indexValue, executiveValue, manifestValue]) => {
        setIndex(indexValue as DataIndex)
        setExec(executiveValue as ExecutiveSummary)
        setManifest(manifestValue as EvidenceManifest)
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : String(reason)))
  }, [])

  const navigate = (next: SiteRoute) => {
    if (window.location.hash === `#${next}`) {
      setRoute(next)
      return
    }
    window.location.hash = next
  }

  if (error) {
    return <main className="loading"><strong>โหลดข้อมูลสุราษฎร์ธานีไม่สำเร็จ</strong><span>{error}</span></main>
  }
  if (!index || !exec || !manifest) return <main className="loading">กำลังเปิด evidence stack 37-STC…</main>

  return (
    <div className="site-shell">
      <PrimaryNav active={route} onNavigate={navigate} />
      <div className="site-content">
        {route === 'history' && <HistoryPage index={index} exec={exec} manifest={manifest} />}
        {route === 'current' && <CurrentEvidencePage index={index} exec={exec} manifest={manifest} />}
        {route === 'drone' && <DroneMultiYearPage />}
        {route === 'report' && <ReportPage index={index} exec={exec} manifest={manifest} />}
        {route === 'map' && <MapExplorerPage index={index} />}
      </div>
    </div>
  )
}
