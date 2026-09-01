import { useEffect, useState } from 'react'
import DroneBaselineInjector, {
  type DroneBaselineSummary,
} from './DroneBaselineInjector'
import './preplantingSpectral.css'

type Props = {
  onOpenHistory: () => void
  onOpenCurrent: () => void
  onOpenProject: () => void
  onOpenCoast: () => void
}

export default function DroneBaselinePage({
  onOpenHistory,
  onOpenCurrent,
  onOpenProject,
  onOpenCoast,
}: Props) {
  const [summary, setSummary] = useState<DroneBaselineSummary | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    fetch('data/project_drone_orthomosaic/summary.json')
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        return response.json()
      })
      .then((value: unknown) => {
        if (active) setSummary(value as DroneBaselineSummary)
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : String(reason))
      })
    return () => {
      active = false
    }
  }, [])

  return (
    <main className="spectral-shell drone-standalone-page">
      <nav className="spectral-nav">
        <div><span>สมุทรสงคราม</span><strong>Coastal Evidence</strong></div>
        <div>
          <button onClick={onOpenHistory}>หลักฐานย้อนหลัง</button>
          <button onClick={onOpenCurrent}>ผล 2023–2026</button>
          <button className="active">ภาพโดรน HR</button>
          <button onClick={onOpenProject}>รายงาน 9 แปลง</button>
          <button onClick={onOpenCoast}>แผนที่ 10 ปี</button>
        </div>
      </nav>

      <section className="drone-page-context">
        <span>HIGH-RESOLUTION REVIEW · SEPARATE EVIDENCE PAGE</span>
        <h1>ภาพโดรนความละเอียดสูง</h1>
        <p>หน้านี้แยกจากสไลเดอร์ดาวเทียมย้อนหลังโดยตั้งใจ เพื่อไม่ให้ baseline โดรน 1 epoch ถูกอ่านปนกับการเปรียบเทียบหลายปีของ Sentinel-2</p>
      </section>

      {error && <section className="drone-page-status">โหลดข้อมูลโดรนไม่สำเร็จ: {error}</section>}
      {!summary && !error && <section className="drone-page-status">กำลังเปิดภาพโดรนทั้ง 9 แปลง…</section>}
      {summary && (
        <section className="drone-standalone-content">
          <DroneBaselineInjector summary={summary} />
          <div className="spectral-compare drone-portal-marker" aria-hidden="true" />
        </section>
      )}
    </main>
  )
}
