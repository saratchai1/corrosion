import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import './plantingEvidence.css'

type ChangeMetrics = {
  start_year: number
  end_year: number
  start_scene_date: string
  end_scene_date: string
  elapsed_days: number
  paired_transect_count: number
  median_nsm_m: number | null
  median_rate_m_per_year: number | null
  class_counts: {
    APPARENT_LANDWARD: number
    WITHIN_20M: number
    APPARENT_SEAWARD: number
  }
  confidence: string
}

type PlotEvidence = {
  plot_id: string
  area_rai: number
  planting_start_date: string | null
  planting_completion_date: string
  first_confirmed_post_completion_observation: {
    year: number
    scene_date: string
    days_from_completion: number
  }
  latest_confirmed_post_completion_observation: {
    year: number
    scene_date: string
    days_from_completion: number
  }
  last_before_completion_observation: {
    year: number
    scene_date: string
    days_from_completion: number
  }
  indicators: {
    waterline: {
      transition_before_completion_to_first_post: ChangeMetrics
      confirmed_post_completion_change: ChangeMetrics
    }
    mangrove_edge_proxy: {
      transition_before_completion_to_first_post: ChangeMetrics
      confirmed_post_completion_change: ChangeMetrics
    }
  }
}

export type PlantingAwareSummary = {
  evidence_level: string
  erosion_effect_conclusion: string
  verified_plot_count: number
  verified_area_rai: number
  verified_plot_ids: string[]
  plots_without_verified_timing: string[]
  timing_interpretation: {
    confirmed_post_completion_scene_years: number[]
    '2024_scene_date': string
    '2024_status': string
    '2024_guard_th': string
    post_completion_guard_th: string
  }
  plots: PlotEvidence[]
  allowed_claim_th: string
  not_allowed_claim_th: string
}

type Props = {
  summary: PlantingAwareSummary
}

function formatThaiDate(value: string): string {
  const [year, month, day] = value.split('-').map(Number)
  return new Intl.DateTimeFormat('th-TH', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(Date.UTC(year, month - 1, day)))
}

function signed(value: number | null): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${value >= 0 ? '+' : ''}${value.toFixed(1)} ม.`
}

function reading(metrics: ChangeMetrics): string {
  const value = metrics.median_nsm_m
  if (value == null) return 'ข้อมูลคู่ยังไม่พอ'
  if (value > 20) return 'กึ่งกลางปรากฏเคลื่อนออกทะเล'
  if (value < -20) return 'กึ่งกลางปรากฏเคลื่อนเข้าฝั่ง'
  return 'กึ่งกลางอยู่ภายในช่วง ±20 ม.'
}

function PlantingEvidencePanel({ summary }: Props) {
  const [plotId, setPlotId] = useState(summary.verified_plot_ids[0] ?? '')
  const plot = summary.plots.find((item) => item.plot_id === plotId) ?? summary.plots[0]

  if (!plot) return null
  const postWaterline = plot.indicators.waterline.confirmed_post_completion_change
  const transitionWaterline = plot.indicators.waterline.transition_before_completion_to_first_post

  return (
    <section className="planting-evidence-panel" id="planting-evidence">
      <header className="planting-evidence-heading">
        <div>
          <span>PROJECT PLANTING EVIDENCE · VERIFIED COMPLETION DATES</span>
          <h2>ข้อมูลวันปลูกที่ยืนยันแล้ว ถูกนำเข้าการวิเคราะห์แล้ว</h2>
          <p>
            ตอนนี้แยกได้จริงว่า ภาพปี 2025 และ 2026 ของ 91-STC, 97-STC และ 98-STC
            อยู่หลังปลูกเสร็จ ส่วนภาพ 15 ก.พ. 2024 อยู่ก่อนวันปลูกเสร็จ แต่ยังห้ามเรียกว่า “ก่อนปลูก” เพราะยังไม่มีวันเริ่มปลูก
          </p>
        </div>
        <div className="planting-evidence-status">
          <strong>{summary.verified_plot_count}/8</strong>
          <span>แปลงชายฝั่งมีวันปลูกเสร็จยืนยันแล้ว</span>
          <small>{summary.verified_area_rai.toFixed(2)} ไร่</small>
        </div>
      </header>

      <div className="planting-evidence-cards">
        {summary.plots.map((item) => (
          <button
            type="button"
            key={item.plot_id}
            className={item.plot_id === plot.plot_id ? 'active' : ''}
            onClick={() => setPlotId(item.plot_id)}
          >
            <span>{item.plot_id}</span>
            <strong>{formatThaiDate(item.planting_completion_date)}</strong>
            <small>ปลูกเสร็จ · {item.area_rai.toFixed(2)} ไร่</small>
          </button>
        ))}
      </div>

      <div className="planting-evidence-detail">
        <div className="planting-evidence-timeline">
          <article className="before-completion">
            <span>ภาพปี 2024</span>
            <strong>{formatThaiDate(plot.last_before_completion_observation.scene_date)}</strong>
            <small>{Math.abs(plot.last_before_completion_observation.days_from_completion)} วันก่อนปลูกเสร็จ</small>
            <em>เริ่มปลูก: ยังไม่ทราบ → จึงไม่ใช่ confirmed pre-plant</em>
          </article>
          <i>→</i>
          <article className="completion">
            <span>วันปลูกเสร็จ</span>
            <strong>{formatThaiDate(plot.planting_completion_date)}</strong>
            <small>{plot.plot_id}</small>
          </article>
          <i>→</i>
          <article className="post-completion">
            <span>ภาพหลังปลูกเสร็จครั้งแรก</span>
            <strong>{formatThaiDate(plot.first_confirmed_post_completion_observation.scene_date)}</strong>
            <small>+{plot.first_confirmed_post_completion_observation.days_from_completion} วัน</small>
          </article>
          <i>→</i>
          <article className="post-completion">
            <span>ภาพล่าสุด</span>
            <strong>{formatThaiDate(plot.latest_confirmed_post_completion_observation.scene_date)}</strong>
            <small>+{plot.latest_confirmed_post_completion_observation.days_from_completion} วัน</small>
          </article>
        </div>

        <div className="planting-evidence-metrics">
          <article>
            <span>ช่วงเปลี่ยนผ่าน 2024 → 2025</span>
            <strong>{signed(transitionWaterline.median_nsm_m)}</strong>
            <small>Median WATERLINE NSM · {transitionWaterline.paired_transect_count} transects</small>
            <p>{reading(transitionWaterline)}</p>
            <em>2024 ยังไม่ใช่ pre-plant ที่ยืนยันแล้ว</em>
          </article>
          <article className="post">
            <span>หลังปลูกเสร็จที่ยืนยันแล้ว 2025 → 2026</span>
            <strong>{signed(postWaterline.median_nsm_m)}</strong>
            <small>Median WATERLINE NSM · {postWaterline.paired_transect_count} transects</small>
            <p>{reading(postWaterline)}</p>
            <em>มีเพียง 2 จุดเวลา · LOW confidence</em>
          </article>
          <article className="classes">
            <span>แนว WATERLINE ปี 2025 → 2026</span>
            <div><b>{postWaterline.class_counts.APPARENT_LANDWARD}</b><small>เข้าฝั่ง &gt;20 ม.</small></div>
            <div><b>{postWaterline.class_counts.WITHIN_20M}</b><small>ภายใน ±20 ม.</small></div>
            <div><b>{postWaterline.class_counts.APPARENT_SEAWARD}</b><small>ออกทะเล &gt;20 ม.</small></div>
          </article>
        </div>
      </div>

      <div className="planting-evidence-guard">
        <div><strong>ตอนนี้พูดได้เพิ่ม</strong><p>{summary.allowed_claim_th}</p></div>
        <div><strong>ยังพูดไม่ได้</strong><p>{summary.not_allowed_claim_th}</p></div>
      </div>

      <p className="planting-evidence-missing">
        ยังขาดวันเริ่มปลูกของ 91/97/98-STC และวันเริ่ม–ปลูกเสร็จของ {summary.plots_without_verified_timing.join(', ')}
      </p>
    </section>
  )
}

export default function PlantingEvidenceInjector({ summary }: Props) {
  const [mount, setMount] = useState<HTMLElement | null>(null)

  useEffect(() => {
    const compare = document.querySelector<HTMLElement>('.spectral-compare')
    const parent = compare?.parentElement
    if (!compare || !parent) return
    const node = document.createElement('div')
    node.className = 'planting-evidence-portal'
    parent.insertBefore(node, compare)
    setMount(node)
    return () => {
      setMount(null)
      node.remove()
    }
  }, [])

  return mount ? createPortal(<PlantingEvidencePanel summary={summary} />, mount) : null
}
