import {
  useMemo,
  useState,
  type KeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from 'react'
import './preplantingHistory.css'

type PeriodMetrics = {
  transect_count: number
  classified_transect_count: number
  median_nsm_m: number | null
  median_epr_m_per_year: number | null
  median_lrr_m_per_year: number | null
  class_counts: Record<string, number>
}

type HistoryScene = {
  year: number
  date: string
  scene_id: string
  image: string
  tide_level_m_msl: number | null
  tide_status: string
  tide_source_tier: string
  waterline_accepted: boolean
}

type PlotIndicator = {
  historical_median_lrr_m_per_year: number | null
  recent_median_lrr_m_per_year: number | null
  trend_change_recent_minus_historical_m_per_year: number | null
  candidate_control_historical_median_lrr_m_per_year: number | null
  candidate_control_recent_median_lrr_m_per_year: number | null
  historical_treatment_minus_control_lrr_m_per_year: number | null
  recent_treatment_minus_control_lrr_m_per_year: number | null
  difference_in_differences_screening_m_per_year: number | null
  historical_class_counts: Record<string, number>
  recent_class_counts: Record<string, number>
  confidence: string
}

type PlotHistory = {
  plot_id: string
  treatment_transect_count: number
  candidate_control_count: number
  waterline: PlotIndicator
  mangrove_edge_proxy: PlotIndicator
}

export type PreplantingHistorySummary = {
  title: string
  generated_at_utc: string
  evidence_level: string
  erosion_effect_conclusion: string
  years: number[]
  periods: {
    historical_preplanting: {
      waterline_years: number[]
      mangrove_edge_proxy_years: number[]
      label_th: string
    }
    recent_monitoring: {
      waterline_years: number[]
      mangrove_edge_proxy_years: number[]
      label_th: string
    }
    intervention_note: string
  }
  scene_selection: {
    current_target_tide_m_msl: number
    maximum_historical_delta_from_target_m: number
    accepted_waterline_years: number[]
    visual_context_only_years: number[]
    accepted_tide_spread_m: number
    display_scenes: HistoryScene[]
    audit_csv: string
  }
  answer_to_preplanting_question: {
    status: string
    headline_th: string
    historical_apparent_landward_fraction: number
    recent_apparent_landward_fraction: number
    historical_median_lrr_m_per_year: number | null
    recent_median_lrr_m_per_year: number | null
    allowed_interpretation_th: string
  }
  indicators: {
    waterline: {
      role: string
      historical_years: number[]
      recent_years: number[]
      historical: PeriodMetrics
      recent: PeriodMetrics
    }
    mangrove_edge_proxy: {
      role: string
      historical_years: number[]
      recent_years: number[]
      area_ha_by_year: Record<string, number>
      historical: PeriodMetrics
      recent: PeriodMetrics
    }
  }
  transects: {
    treatment_count: number
    reference_geometry: string
    position_convention: string
    screening_threshold_m: number
  }
  controls: {
    source: string
    status: string
    scientific_limit: string
  }
  per_plot: PlotHistory[]
  allowed_claim_th: string
  limitations: string[]
  source_data: Record<string, string>
}

type Props = {
  history: PreplantingHistorySummary
  onOpenCurrent: () => void
  onOpenProject: () => void
  onOpenCoast: () => void
}

function signed(value: number | null, digits = 1): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${value >= 0 ? '+' : ''}${value.toFixed(digits)}`
}

function pct(count: number, total: number): string {
  return total ? `${((count / total) * 100).toFixed(1)}%` : '—'
}

function counts(period: PeriodMetrics) {
  return {
    landward: period.class_counts.APPARENT_LANDWARD ?? 0,
    within: period.class_counts.WITHIN_20M ?? 0,
    seaward: period.class_counts.APPARENT_SEAWARD ?? 0,
    insufficient: period.class_counts.INSUFFICIENT_DATA ?? 0,
  }
}

function sceneRole(year: number): string {
  if (year <= 2023) return 'ก่อนช่วงดำเนินการ'
  if (year === 2024) return 'ช่วงดำเนินการ*'
  return 'ช่วงติดตามล่าสุด'
}

function sourceLabel(scene: HistoryScene): string {
  if (scene.tide_source_tier === 'official_hourly_prediction') return 'รายชั่วโมงทางการ'
  if (scene.tide_source_tier === 'secondary_published_extrema') return 'ประมาณจากจุดน้ำขึ้น–ลง'
  return 'ไม่มีระดับน้ำสำหรับคัดกรอง'
}

function PeriodBar({ period }: { period: PeriodMetrics }) {
  const value = counts(period)
  const total = Math.max(period.transect_count, 1)
  return (
    <div className="history-period-bar" aria-label="สัดส่วนการเคลื่อนที่ของแนววิเคราะห์">
      <span className="landward" style={{ flex: Math.max(value.landward, 0.25) }} title={`เข้าฝั่ง ${value.landward}/${total}`} />
      <span className="within" style={{ flex: Math.max(value.within, 0.25) }} title={`ภายใน ±20 ม. ${value.within}/${total}`} />
      <span className="seaward" style={{ flex: Math.max(value.seaward, 0.25) }} title={`ออกทะเล ${value.seaward}/${total}`} />
      {value.insufficient > 0 && <span className="insufficient" style={{ flex: value.insufficient }} title={`ข้อมูลไม่พอ ${value.insufficient}/${total}`} />}
    </div>
  )
}

function PeriodCard({
  title,
  subtitle,
  period,
}: {
  title: string
  subtitle: string
  period: PeriodMetrics
}) {
  const value = counts(period)
  return (
    <article className="history-period-card">
      <header>
        <div><span>{subtitle}</span><h3>{title}</h3></div>
        <strong>{period.classified_transect_count}<small>แนวที่จัดกลุ่มได้</small></strong>
      </header>
      <PeriodBar period={period} />
      <div className="history-period-counts">
        <div className="landward"><strong>{value.landward}</strong><span>เข้าฝั่ง &gt;20 ม.</span><small>{pct(value.landward, period.classified_transect_count)}</small></div>
        <div className="within"><strong>{value.within}</strong><span>ภายใน ±20 ม.</span><small>{pct(value.within, period.classified_transect_count)}</small></div>
        <div className="seaward"><strong>{value.seaward}</strong><span>ออกทะเล &gt;20 ม.</span><small>{pct(value.seaward, period.classified_transect_count)}</small></div>
      </div>
      <dl>
        <div><dt>Median NSM</dt><dd>{signed(period.median_nsm_m)} ม.</dd></div>
        <div><dt>Median LRR</dt><dd>{signed(period.median_lrr_m_per_year)} ม./ปี</dd></div>
      </dl>
    </article>
  )
}

function HistorySwipe({ scenes }: { scenes: HistoryScene[] }) {
  const ordered = useMemo(() => [...scenes].sort((a, b) => a.year - b.year), [scenes])
  const [beforeYear, setBeforeYear] = useState(2020)
  const [afterYear, setAfterYear] = useState(2026)
  const [split, setSplit] = useState(50)
  const [focus, setFocus] = useState(true)
  const before = ordered.find((scene) => scene.year === beforeYear) ?? ordered[0]
  const after = ordered.find((scene) => scene.year === afterYear) ?? ordered[ordered.length - 1]

  const updateSplit = (clientX: number, element: HTMLDivElement) => {
    const bounds = element.getBoundingClientRect()
    const next = ((clientX - bounds.left) / Math.max(bounds.width, 1)) * 100
    setSplit(Math.max(0, Math.min(100, Math.round(next))))
  }

  const pointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId)
    updateSplit(event.clientX, event.currentTarget)
  }

  const pointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      updateSplit(event.clientX, event.currentTarget)
    }
  }

  const keyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'ArrowLeft') setSplit((value) => Math.max(0, value - 2))
    if (event.key === 'ArrowRight') setSplit((value) => Math.min(100, value + 2))
    if (event.key === 'Home') setSplit(0)
    if (event.key === 'End') setSplit(100)
  }

  const setPair = (left: number, right: number) => {
    setBeforeYear(left)
    setAfterYear(right)
    setSplit(50)
  }

  const tideDifference = before.tide_level_m_msl != null && after.tide_level_m_msl != null
    ? Math.abs(after.tide_level_m_msl - before.tide_level_m_msl)
    : null

  return (
    <section className="history-card history-swipe-card" id="history-compare">
      <div className="history-section-title">
        <div><span>ภาพ Sentinel-2 จริง · 2017–2026</span><h2>เทียบภาพก่อนปลูกกับช่วงล่าสุด</h2></div>
        <p>ลากเส้นบนภาพโดยตรง · สีของน้ำไม่ใช่หลักฐานการกัดเซาะ</p>
      </div>

      <div className="history-quick-pairs">
        <span>คู่แนะนำ</span>
        <button className={beforeYear === 2020 && afterYear === 2023 ? 'active' : ''} onClick={() => setPair(2020, 2023)}>2020 → 2023</button>
        <button className={beforeYear === 2020 && afterYear === 2026 ? 'active' : ''} onClick={() => setPair(2020, 2026)}>2020 → 2026</button>
        <button className={beforeYear === 2023 && afterYear === 2026 ? 'active' : ''} onClick={() => setPair(2023, 2026)}>2023 → 2026</button>
      </div>

      <div className="history-swipe-toolbar">
        <label><span>ก่อน / Before</span><select value={before.year} onChange={(event) => {
          const year = Number(event.target.value)
          setBeforeYear(year)
          if (year >= afterYear) {
            const next = ordered.find((scene) => scene.year > year)
            if (next) setAfterYear(next.year)
          }
        }}>{ordered.map((scene) => <option key={scene.year} value={scene.year} disabled={scene.year >= afterYear}>{scene.year} · {scene.waterline_accepted ? 'คุมระดับน้ำ' : 'ดูภาพเท่านั้น'}</option>)}</select></label>
        <div className="history-focus-toggle">
          <button className={focus ? 'active' : ''} onClick={() => setFocus(true)}>โฟกัส 91–98 STC</button>
          <button className={!focus ? 'active' : ''} onClick={() => setFocus(false)}>เต็ม AOI</button>
        </div>
        <label><span>หลัง / After</span><select value={after.year} onChange={(event) => {
          const year = Number(event.target.value)
          setAfterYear(year)
          if (year <= beforeYear) {
            const previous = [...ordered].reverse().find((scene) => scene.year < year)
            if (previous) setBeforeYear(previous.year)
          }
        }}>{ordered.map((scene) => <option key={scene.year} value={scene.year} disabled={scene.year <= beforeYear}>{scene.year} · {scene.waterline_accepted ? 'คุมระดับน้ำ' : 'ดูภาพเท่านั้น'}</option>)}</select></label>
      </div>

      <div
        className={`history-swipe-stage ${focus ? 'focus-coast' : ''}`}
        role="slider"
        tabIndex={0}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={split}
        aria-label={`เปรียบเทียบภาพปี ${before.year} กับ ${after.year}`}
        onPointerDown={pointerDown}
        onPointerMove={pointerMove}
        onKeyDown={keyDown}
      >
        <img src={after.image} alt={`ภาพ Sentinel-2 ปี ${after.year}`} draggable={false} />
        <img className="before" src={before.image} alt={`ภาพ Sentinel-2 ปี ${before.year}`} draggable={false} style={{ clipPath: `inset(0 ${100 - split}% 0 0)` }} />
        <div className="history-divider" style={{ left: `${split}%` }} />
        <div className="history-image-label before-label"><span>ก่อน</span><strong>{before.year}</strong><small>{before.date}</small></div>
        <div className="history-image-label after-label"><span>หลัง</span><strong>{after.year}</strong><small>{after.date}</small></div>
      </div>

      <div className="history-scene-pair-meta">
        {[before, after].map((scene) => (
          <article key={`${scene.year}-${scene.scene_id}`} className={scene.waterline_accepted ? 'accepted' : 'visual-only'}>
            <span>{scene.year === before.year ? 'ภาพก่อน' : 'ภาพหลัง'} · {sceneRole(scene.year)}</span>
            <strong>{scene.year} <small>{scene.date}</small></strong>
            <p>{scene.tide_level_m_msl == null ? 'ไม่มีค่าระดับน้ำสำหรับภาพนี้' : `${scene.tide_level_m_msl.toFixed(3)} m MSL · ${sourceLabel(scene)}`}</p>
            <em>{scene.waterline_accepted ? 'ใช้วิเคราะห์ WATERLINE ได้ในระดับ screening' : 'ใช้เป็นบริบทภาพ/ขอบพืชเท่านั้น'}</em>
          </article>
        ))}
        <div className={`history-tide-gap ${tideDifference != null && tideDifference <= 0.4 ? 'accepted' : 'review'}`}>
          <span>ต่างระดับน้ำ</span><strong>{tideDifference == null ? '—' : tideDifference.toFixed(3)}</strong><small>เมตร MSL</small>
        </div>
      </div>
    </section>
  )
}

function TideTimeline({ history }: { history: PreplantingHistorySummary }) {
  const target = history.scene_selection.current_target_tide_m_msl
  const scenes = history.scene_selection.display_scenes
  const values = scenes.filter((scene) => scene.tide_level_m_msl != null).map((scene) => scene.tide_level_m_msl as number)
  const lower = Math.min(...values, target) - 0.08
  const upper = Math.max(...values, target) + 0.08
  const position = (value: number) => ((value - lower) / Math.max(upper - lower, 0.001)) * 100

  return (
    <section className="history-card history-tide-card">
      <div className="history-section-title">
        <div><span>ระดับน้ำของภาพที่ใช้</span><h2>ปีใดใช้วิเคราะห์ Waterline ได้</h2></div>
        <strong>{history.scene_selection.accepted_tide_spread_m.toFixed(3)} ม. spread</strong>
      </div>
      <div className="history-tide-axis">
        <div className="axis-line" />
        <div className="target" style={{ left: `${position(target)}%` }}><i /><span>เป้าหมาย {target.toFixed(3)}</span></div>
        {scenes.filter((scene) => scene.tide_level_m_msl != null).map((scene, index) => (
          <div className={`point ${scene.waterline_accepted ? 'accepted' : 'rejected'}`} key={scene.year} style={{ left: `${position(scene.tide_level_m_msl as number)}%`, top: `${38 + (index % 2) * 46}px` }}>
            <i /><strong>{scene.year}</strong><span>{(scene.tide_level_m_msl as number).toFixed(3)}</span>
          </div>
        ))}
      </div>
      <div className="history-tide-axis-labels"><span>{lower.toFixed(2)} m MSL</span><span>{upper.toFixed(2)} m MSL</span></div>
      <div className="history-tide-legend"><span><i className="accepted" />ใช้ทำ Waterline</span><span><i className="rejected" />ระดับน้ำห่างเกณฑ์</span><span><i className="missing" />2017–2019 ไม่มีข้อมูลจากเว็บ</span></div>
      <p>
        ข้อมูลจากเว็บพบครบรายเดือนสำหรับปี 2020–2022 แต่ภาพปี 2022 ที่มีอยู่ถ่ายที่ระดับน้ำ {scenes.find((scene) => scene.year === 2022)?.tide_level_m_msl?.toFixed(3)} m MSL ซึ่งห่างจากเป้าหมายเกิน {history.scene_selection.maximum_historical_delta_from_target_m.toFixed(2)} ม. จึงไม่ถูกใช้คำนวณ Waterline
      </p>
    </section>
  )
}

function PlotHistoryExplorer({ plots }: { plots: PlotHistory[] }) {
  const coastal = useMemo(() => plots.filter((plot) => plot.treatment_transect_count > 0), [plots])
  const ranked = useMemo(() => [...coastal].sort((left, right) => {
    const leftHistorical = left.waterline.historical_class_counts.APPARENT_LANDWARD ?? 0
    const leftRecent = left.waterline.recent_class_counts.APPARENT_LANDWARD ?? 0
    const rightHistorical = right.waterline.historical_class_counts.APPARENT_LANDWARD ?? 0
    const rightRecent = right.waterline.recent_class_counts.APPARENT_LANDWARD ?? 0
    const leftScore = (leftHistorical - leftRecent) / Math.max(left.treatment_transect_count, 1)
    const rightScore = (rightHistorical - rightRecent) / Math.max(right.treatment_transect_count, 1)
    return rightScore - leftScore
  }), [coastal])
  const [selectedId, setSelectedId] = useState(ranked[0]?.plot_id ?? '97-STC')
  const selected = coastal.find((plot) => plot.plot_id === selectedId) ?? ranked[0]
  if (!selected) return null

  const historical = selected.waterline.historical_class_counts
  const recent = selected.waterline.recent_class_counts
  const histLandward = historical.APPARENT_LANDWARD ?? 0
  const recentLandward = recent.APPARENT_LANDWARD ?? 0
  const histWithin = historical.WITHIN_20M ?? 0
  const recentWithin = recent.WITHIN_20M ?? 0
  const histSeaward = historical.APPARENT_SEAWARD ?? 0
  const recentSeaward = recent.APPARENT_SEAWARD ?? 0

  return (
    <section className="history-card history-plot-card">
      <div className="history-section-title">
        <div><span>ผลรายแปลง · WATERLINE</span><h2>จุดใดมีสัญญาณถอยก่อนปี 2023</h2></div>
        <p>เรียงจากสัดส่วนที่ดีขึ้นมากที่สุด ไม่ใช่อันดับผลสำเร็จของโครงการ</p>
      </div>
      <div className="history-plot-tabs">
        {ranked.map((plot) => {
          const before = plot.waterline.historical_class_counts.APPARENT_LANDWARD ?? 0
          const after = plot.waterline.recent_class_counts.APPARENT_LANDWARD ?? 0
          return <button className={plot.plot_id === selected.plot_id ? 'active' : ''} key={plot.plot_id} onClick={() => setSelectedId(plot.plot_id)}><strong>{plot.plot_id}</strong><span>{before} → {after} แนวเข้าฝั่ง</span></button>
        })}
      </div>
      <div className="history-plot-result">
        <header><div><span>แปลงที่เลือก</span><h3>{selected.plot_id}</h3></div><strong>{selected.treatment_transect_count}<small>transects</small></strong></header>
        <div className="history-plot-periods">
          <article><span>ก่อนปี 2023</span><strong>{histLandward}/{selected.treatment_transect_count}</strong><small>แนวปรากฏเข้าฝั่ง · {pct(histLandward, selected.treatment_transect_count)}</small><dl><div><dt>ใน ±20 ม.</dt><dd>{histWithin}</dd></div><div><dt>ออกทะเล</dt><dd>{histSeaward}</dd></div></dl></article>
          <i>→</i>
          <article className="recent"><span>ช่วง 2023–2026</span><strong>{recentLandward}/{selected.treatment_transect_count}</strong><small>แนวปรากฏเข้าฝั่ง · {pct(recentLandward, selected.treatment_transect_count)}</small><dl><div><dt>ใน ±20 ม.</dt><dd>{recentWithin}</dd></div><div><dt>ออกทะเล</dt><dd>{recentSeaward}</dd></div></dl></article>
        </div>
        <div className="history-plot-reading">
          <strong>{histLandward > recentLandward ? 'สัญญาณถอยเข้าฝั่งลดลงในช่วงล่าสุด' : 'ยังไม่เห็นการลดลงของแนวเข้าฝั่งอย่างชัดเจน'}</strong>
          <p>
            ข้อสังเกตนี้เปรียบเทียบช่วงเวลาเท่านั้น Candidate controls จำนวน {selected.candidate_control_count} แนวยังไม่ได้ตรวจโครงสร้างชายฝั่ง การขุดลอก การถม และประวัติปลูก จึงไม่ใช่ผลเชิงเหตุ–ผล
          </p>
        </div>
      </div>
    </section>
  )
}

export default function PreplantingHistoryDashboard({ history, onOpenCurrent, onOpenProject, onOpenCoast }: Props) {
  const waterline = history.indicators.waterline
  const mangrove = history.indicators.mangrove_edge_proxy
  const beforeCounts = counts(waterline.historical)
  const recentCounts = counts(waterline.recent)
  const historicalFraction = history.answer_to_preplanting_question.historical_apparent_landward_fraction
  const recentFraction = history.answer_to_preplanting_question.recent_apparent_landward_fraction
  const fractionChange = (historicalFraction - recentFraction) * 100

  return (
    <main className="history-shell">
      <nav className="history-nav">
        <div><span>สมุทรสงคราม</span><strong>Coastal History Evidence</strong></div>
        <div className="history-nav-tabs">
          <button className="active">ก่อนปลูกเคยกัดเซาะไหม</button>
          <button onClick={onOpenCurrent}>ผล 2023–2026</button>
          <button onClick={onOpenProject}>รายงาน 9 แปลง</button>
          <button onClick={onOpenCoast}>แผนที่ 10 ปี</button>
        </div>
      </nav>

      <header className="history-hero">
        <div className="history-hero-copy">
          <span className="history-kicker">PRE-PLANTING CONTEXT · SENTINEL-2 · 2017–2026</span>
          <h1>ก่อนปี 2023<br /><em>ชายฝั่งเคยถอยหรือไม่?</em></h1>
          <p>
            เพิ่มภาพย้อนหลังสิบปี แล้วแยกช่วงก่อนดำเนินการออกจากช่วงติดตามล่าสุด โดยใช้ Waterline เฉพาะปีที่ระดับน้ำอยู่ใกล้เกณฑ์เดียวกัน และใช้ขอบพืชเป็นหลักฐานคัดกรองอีกชั้นหนึ่ง
          </p>
          <div className="history-hero-actions"><a href="#history-findings">ดูข้อค้นพบ</a><a href="#history-compare">เลื่อนภาพก่อน–หลัง</a></div>
        </div>
        <article className="history-verdict">
          <span>{history.evidence_level.replaceAll('_', ' ')}</span>
          <h2>พบสัญญาณก่อนปี 2023<br /><em>มากกว่าในช่วงล่าสุดบางตำแหน่ง</em></h2>
          <p>{history.answer_to_preplanting_question.headline_th}</p>
          <strong>ยังไม่พิสูจน์ว่าแนวโน้มดีขึ้นเพราะการปลูก</strong>
          <small>EROSION EFFECT: {history.erosion_effect_conclusion}</small>
        </article>
      </header>

      <section className="history-kpis" id="history-findings">
        <article><span>ภาพดาวเทียมย้อนหลัง</span><strong>2017–2026</strong><small>10 annual Sentinel-2 scenes</small></article>
        <article><span>Waterline ที่คุมระดับน้ำได้</span><strong>{history.scene_selection.accepted_waterline_years.length}</strong><small>{history.scene_selection.accepted_waterline_years.join(', ')}</small></article>
        <article className="caution"><span>ก่อนปี 2023 ปรากฏเข้าฝั่ง</span><strong>{beforeCounts.landward}</strong><small>{pct(beforeCounts.landward, waterline.historical.classified_transect_count)} ของแนวที่จัดกลุ่มได้</small></article>
        <article className="positive"><span>ช่วง 2023–2026 ปรากฏเข้าฝั่ง</span><strong>{recentCounts.landward}</strong><small>{pct(recentCounts.landward, waterline.recent.classified_transect_count)}</small></article>
        <article><span>สัดส่วนแนวเข้าฝั่งลดลง</span><strong>{fractionChange.toFixed(1)}</strong><small>percentage points · screening</small></article>
        <article><span>Transects หน้าแปลง</span><strong>{history.transects.treatment_count}</strong><small>91–98 STC</small></article>
      </section>

      <section className="history-card history-answer-card">
        <div className="history-answer-main">
          <span>คำตอบจากข้อมูลที่มีตอนนี้</span>
          <h2>ก่อนปี 2023 <em>มีสัญญาณการถอยเข้าฝั่งจริงในบางช่วง</em> แต่ไม่ใช่การกัดเซาะพร้อมกันทั่วพื้นที่</h2>
          <p>
            Waterline ที่คัดตามระดับน้ำพบแนวปรากฏเข้าฝั่ง {beforeCounts.landward} จาก {waterline.historical.classified_transect_count} แนวก่อนปี 2023 เทียบกับ {recentCounts.landward} จาก {waterline.recent.classified_transect_count} แนวในช่วง 2023–2026 ขณะที่ค่ากึ่งกลาง LRR ของทั้งสองช่วงยังเท่ากับ {signed(waterline.historical.median_lrr_m_per_year)} ม./ปี
          </p>
        </div>
        <div className="history-answer-guard">
          <strong>ข้อความที่ใช้ได้</strong><p>{history.allowed_claim_th}</p>
          <strong>ข้อความที่ยังใช้ไม่ได้</strong><p>“ตั้งแต่ปลูกแล้วการกัดเซาะหยุดลง” เพราะวันปลูกยังไม่ยืนยันและ controls ยังไม่ได้ตรวจปัจจัยรบกวน</p>
        </div>
      </section>

      <section className="history-period-grid">
        <PeriodCard title="ก่อนช่วงดำเนินการ" subtitle={history.periods.historical_preplanting.label_th} period={waterline.historical} />
        <div className="history-period-change"><span>แนวเข้าฝั่ง</span><strong>{beforeCounts.landward} → {recentCounts.landward}</strong><small>ลดลง {fractionChange.toFixed(1)} จุดร้อยละ</small><i>แต่ยังไม่ใช่ causal effect</i></div>
        <PeriodCard title="ช่วงติดตามล่าสุด" subtitle={history.periods.recent_monitoring.label_th} period={waterline.recent} />
      </section>

      <HistorySwipe scenes={history.scene_selection.display_scenes} />

      <section className="history-imagery-timeline history-card">
        <div className="history-section-title"><div><span>ANNUAL IMAGE RECORD</span><h2>ภาพจริงครบสิบปี</h2></div><p>กรอบเขียว = ใช้ Waterline · กรอบเทา = ใช้ดูบริบท/ขอบพืช</p></div>
        <div className="history-scene-grid">
          {history.scene_selection.display_scenes.map((scene) => <figure className={scene.waterline_accepted ? 'accepted' : 'visual-only'} key={scene.year}><a href={scene.image} target="_blank" rel="noreferrer"><img src={scene.image} alt={`ภาพดาวเทียม Sentinel-2 สมุทรสงคราม ปี ${scene.year}`} /><span>{scene.waterline_accepted ? 'WATERLINE' : 'VISUAL ONLY'}</span></a><figcaption><strong>{scene.year}</strong><small>{scene.date}</small><p>{scene.tide_level_m_msl == null ? 'ไม่มีระดับน้ำจากเว็บ' : `${scene.tide_level_m_msl.toFixed(3)} m MSL`}</p></figcaption></figure>)}
        </div>
      </section>

      <TideTimeline history={history} />

      <section className="history-card history-proxy-card">
        <div className="history-section-title"><div><span>MANGROVE EDGE PROXY</span><h2>ขอบพืชให้สัญญาณที่ต่างกันชัดกว่า Waterline</h2></div><strong>LOW confidence</strong></div>
        <div className="history-proxy-comparison">
          <article><span>2017–2023</span><strong>{signed(mangrove.historical.median_nsm_m)} ม.</strong><small>Median NSM · LRR {signed(mangrove.historical.median_lrr_m_per_year)} ม./ปี</small><PeriodBar period={mangrove.historical} /><p>{counts(mangrove.historical).landward} แนวเข้าฝั่ง · {counts(mangrove.historical).seaward} แนวออกทะเล</p></article>
          <i>→</i>
          <article className="recent"><span>2023–2026</span><strong>{signed(mangrove.recent.median_nsm_m)} ม.</strong><small>Median NSM · LRR {signed(mangrove.recent.median_lrr_m_per_year)} ม./ปี</small><PeriodBar period={mangrove.recent} /><p>{counts(mangrove.recent).landward} แนวเข้าฝั่ง · {counts(mangrove.recent).seaward} แนวออกทะเล</p></article>
        </div>
        <p className="history-warning">นี่คือขอบพืชจาก NDVI ≥ 0.35 ไม่ใช่ขอบป่าชายเลนที่ตรวจรับแล้ว การเปลี่ยนแปลงอาจรวมผลจากน้ำท่วม เงา ความขุ่น การจัดแนวกริด และพืชชนิดอื่น จึงต้องตรวจด้วยโดรนก่อนนำไปเคลม</p>
      </section>

      <PlotHistoryExplorer plots={history.per_plot} />

      <section className="history-method-grid">
        <article><span>01</span><strong>ภาพย้อนหลัง</strong><p>ใช้ Sentinel-2 ช่วงมกราคม–เมษายน ปี 2017–2026 และยึด transect ชุดเดียวกับผลปัจจุบัน</p></article>
        <article><span>02</span><strong>ระดับน้ำ</strong><p>พบข้อมูลจาก ThailandTideTables ครบปี 2020–2022 แล้วแปลงเป็น MSL ด้วย offset 2.14 ม. ที่ตรวจเทียบกับตารางทางการปี 2026</p></article>
        <article><span>03</span><strong>แยกสองช่วง</strong><p>เปรียบเทียบก่อนปี 2023 กับช่วง 2023–2026 โดยไม่ใช้ปี 2024 เป็นวันเริ่มผลกระทบที่แน่นอน</p></article>
        <article><span>04</span><strong>ไม่สรุปสาเหตุ</strong><p>ผลต่างก่อน–หลังเป็นหลักฐานเชิงเวลา ไม่ใช่ข้อพิสูจน์ว่าการปลูกเป็นสาเหตุ</p></article>
      </section>

      <details className="history-details">
        <summary>ข้อจำกัดและไฟล์ตรวจสอบ</summary>
        <div><ul>{history.limitations.map((item) => <li key={item}>{item}</li>)}</ul><nav><a href="data/project_preplanting_history/summary.json" target="_blank" rel="noreferrer">Summary JSON</a><a href="data/project_preplanting_history/treatment_transects_periods.geojson" target="_blank" rel="noreferrer">Transect GeoJSON</a></nav></div>
      </details>

      <footer className="history-footer">
        <div><strong>สถานะหลักฐาน</strong><span>{history.evidence_level}</span></div>
        <p>{history.periods.intervention_note}</p>
        <small>Generated {new Date(history.generated_at_utc).toLocaleString('th-TH')}</small>
      </footer>
    </main>
  )
}
