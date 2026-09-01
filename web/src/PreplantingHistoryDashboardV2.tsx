import {
  useMemo,
  useState,
  type KeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from 'react'
import './preplantingSpectral.css'

type PeriodMetrics = {
  transect_count: number
  classified_transect_count: number
  median_nsm_m: number | null
  median_epr_m_per_year: number | null
  median_lrr_m_per_year: number | null
  class_counts: Record<string, number>
}

type VisualMode = {
  label_th: string
  short_th: string
  description_th: string
  evidence_role: string
}

type VisualView = {
  label_th: string
  description_th: string
}

type HistoryScene = {
  year: number
  date: string
  scene_id: string
  image: string
  context_image?: string
  tide_level_m_msl: number | null
  tide_status: string
  tide_source_tier: string
  waterline_accepted: boolean
  visuals?: Record<string, Record<string, string>>
}

type PlotIndicator = {
  historical_median_lrr_m_per_year: number | null
  recent_median_lrr_m_per_year: number | null
  trend_change_recent_minus_historical_m_per_year: number | null
  candidate_control_historical_median_lrr_m_per_year: number | null
  candidate_control_recent_median_lrr_m_per_year: number | null
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

export type PreplantingHistorySummaryV2 = {
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
  }
  visualization?: {
    default_view: string
    default_mode: string
    views: Record<string, VisualView>
    modes: Record<string, VisualMode>
    image_count: number
    background_source: string
    analysis_overlay_source: string
    scientific_guard_th: string
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
    screening_threshold_m: number
  }
  controls: {
    status: string
    scientific_limit: string
  }
  per_plot: PlotHistory[]
  allowed_claim_th: string
  limitations: string[]
}

type Props = {
  history: PreplantingHistorySummaryV2
  onOpenCurrent: () => void
  onOpenDrone: () => void
  onOpenProject: () => void
  onOpenCoast: () => void
}

type ModeKey = 'rgb' | 'false_vegetation' | 'ndvi' | 'mndwi' | 'swir'
type ViewKey = 'focus' | 'full'

const FALLBACK_MODES: Record<ModeKey, VisualMode> = {
  rgb: {
    label_th: 'สีจริง RGB',
    short_th: 'สีจริง',
    description_th: 'ใช้ดูตำแหน่ง เมือง คลอง และรูปทรงชายฝั่ง',
    evidence_role: 'ORIENTATION',
  },
  false_vegetation: {
    label_th: 'สีเทียมพืช NIR–R–G',
    short_th: 'พืชสีแดง',
    description_th: 'พืชสะท้อน NIR สูงและเห็นเด่นเป็นสีแดง',
    evidence_role: 'MANGROVE_EDGE_SUPPORT',
  },
  ndvi: {
    label_th: 'NDVI ความเขียว',
    short_th: 'NDVI',
    description_th: 'พืชหนาแน่นเป็นสีเขียวเข้ม',
    evidence_role: 'MANGROVE_EDGE_PRIMARY_SCREENING',
  },
  mndwi: {
    label_th: 'MNDWI น้ำ–แผ่นดิน',
    short_th: 'MNDWI',
    description_th: 'น้ำที่ตอบสนองสูงเป็นสีน้ำเงิน',
    evidence_role: 'WATERLINE_PRIMARY_SPECTRAL_VIEW',
  },
  swir: {
    label_th: 'SWIR–NIR–Red ความชื้น',
    short_th: 'SWIR',
    description_th: 'ช่วยแยกน้ำ พื้นชื้น ดินเปิด และพืช',
    evidence_role: 'MOISTURE_AND_WET_SOIL_SUPPORT',
  },
}

const MODE_ORDER: ModeKey[] = ['rgb', 'false_vegetation', 'ndvi', 'mndwi', 'swir']

function signed(value: number | null, digits = 1): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${value >= 0 ? '+' : ''}${value.toFixed(digits)}`
}

function percent(count: number, total: number): string {
  if (!total) return '—'
  return `${((count / total) * 100).toFixed(1)}%`
}

function periodCounts(period: PeriodMetrics) {
  return {
    landward: period.class_counts.APPARENT_LANDWARD ?? 0,
    within: period.class_counts.WITHIN_20M ?? 0,
    seaward: period.class_counts.APPARENT_SEAWARD ?? 0,
    insufficient: period.class_counts.INSUFFICIENT_DATA ?? 0,
  }
}

function sceneImage(scene: HistoryScene, view: ViewKey, mode: ModeKey): string {
  return (
    scene.visuals?.[view]?.[mode]
    ?? scene.context_image
    ?? `data/imagery/${scene.year}.webp`
  )
}

function modeLegend(mode: ModeKey) {
  if (mode === 'ndvi') {
    return (
      <div className="spectral-legend index ndvi">
        <span>น้ำ / ไม่มีพืช</span><i /><span>ดิน–พืชบาง</span><i /><span>พืชหนาแน่น</span>
      </div>
    )
  }
  if (mode === 'mndwi') {
    return (
      <div className="spectral-legend index mndwi">
        <span>ดิน / พืช</span><i /><span>ขอบเปลี่ยนผ่าน</span><i /><span>น้ำตอบสนองสูง</span>
      </div>
    )
  }
  if (mode === 'false_vegetation') {
    return <div className="spectral-legend text"><b className="red" />พืชเด่นเป็นสีแดง <b className="dark" />น้ำและเงามืด</div>
  }
  if (mode === 'swir') {
    return <div className="spectral-legend text"><b className="cyan" />พืช/ความชื้นต่างกัน <b className="dark" />น้ำมักมืด <b className="pink" />ดินเปิด/สิ่งปลูกสร้างเด่นขึ้น</div>
  }
  return <div className="spectral-legend text"><b className="green" />ป่าชายเลน <b className="blue" />น้ำ <b className="grey" />เมืองและโครงสร้าง</div>
}

function SpectralCompare({ history }: { history: PreplantingHistorySummaryV2 }) {
  const scenes = useMemo(
    () => [...history.scene_selection.display_scenes].sort((left, right) => left.year - right.year),
    [history.scene_selection.display_scenes],
  )
  const [beforeYear, setBeforeYear] = useState(2020)
  const [afterYear, setAfterYear] = useState(2026)
  const [mode, setMode] = useState<ModeKey>((history.visualization?.default_mode as ModeKey) || 'rgb')
  const [view, setView] = useState<ViewKey>((history.visualization?.default_view as ViewKey) || 'focus')
  const [split, setSplit] = useState(50)

  const before = scenes.find((scene) => scene.year === beforeYear) ?? scenes[0]
  const after = scenes.find((scene) => scene.year === afterYear) ?? scenes[scenes.length - 1]
  const modes = history.visualization?.modes ?? FALLBACK_MODES
  const currentMode = modes[mode] ?? FALLBACK_MODES[mode]
  const views = history.visualization?.views ?? {
    focus: { label_th: 'โฟกัส 91–98 STC', description_th: 'แนวหน้าแปลงชายฝั่ง' },
    full: { label_th: 'เต็มพื้นที่ 9 แปลง', description_th: 'รวม 87-VSD' },
  }

  const updateSplit = (clientX: number, element: HTMLDivElement) => {
    const bounds = element.getBoundingClientRect()
    const value = ((clientX - bounds.left) / Math.max(bounds.width, 1)) * 100
    setSplit(Math.max(0, Math.min(100, Math.round(value))))
  }

  const onPointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId)
    updateSplit(event.clientX, event.currentTarget)
  }

  const onPointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      updateSplit(event.clientX, event.currentTarget)
    }
  }

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'ArrowLeft') setSplit((value) => Math.max(0, value - 2))
    if (event.key === 'ArrowRight') setSplit((value) => Math.min(100, value + 2))
    if (event.key === 'Home') setSplit(0)
    if (event.key === 'End') setSplit(100)
  }

  const choosePair = (left: number, right: number) => {
    setBeforeYear(left)
    setAfterYear(right)
    setSplit(50)
  }

  const tideGap = before.tide_level_m_msl != null && after.tide_level_m_msl != null
    ? Math.abs(before.tide_level_m_msl - after.tide_level_m_msl)
    : null

  return (
    <section className="spectral-card spectral-compare" id="history-compare">
      <header className="spectral-section-heading">
        <div>
          <span>CONTEXTUAL MULTISPECTRAL COMPARE</span>
          <h2>ดูตำแหน่งจริง และเปลี่ยนสีให้ตรงกับคำถาม</h2>
        </div>
        <p>พื้นหลังเป็นภาพบริบทเต็มพื้นที่ ส่วนกรอบเหลืองคือภาพจาก scene ที่ใช้วิเคราะห์จริง</p>
      </header>

      <div className="spectral-mode-tabs" role="tablist" aria-label="เลือกชนิดภาพดาวเทียม">
        {MODE_ORDER.map((key) => {
          const item = modes[key] ?? FALLBACK_MODES[key]
          return (
            <button
              key={key}
              className={mode === key ? 'active' : ''}
              onClick={() => setMode(key)}
              role="tab"
              aria-selected={mode === key}
            >
              <strong>{item.short_th}</strong>
              <small>{item.label_th}</small>
            </button>
          )
        })}
      </div>

      <div className="spectral-mode-explainer">
        <div><strong>{currentMode.label_th}</strong><p>{currentMode.description_th}</p></div>
        {modeLegend(mode)}
        <em>{currentMode.evidence_role.replaceAll('_', ' ')}</em>
      </div>

      <div className="spectral-controls">
        <label>
          <span>ภาพก่อน</span>
          <select value={before.year} onChange={(event) => setBeforeYear(Number(event.target.value))}>
            {scenes.map((scene) => (
              <option key={scene.year} value={scene.year} disabled={scene.year >= after.year}>
                {scene.year} · {scene.waterline_accepted ? 'คุมระดับน้ำ' : 'บริบทภาพ'}
              </option>
            ))}
          </select>
        </label>
        <div className="spectral-quick-pairs">
          <button className={before.year === 2020 && after.year === 2023 ? 'active' : ''} onClick={() => choosePair(2020, 2023)}>2020 → 2023</button>
          <button className={before.year === 2020 && after.year === 2026 ? 'active' : ''} onClick={() => choosePair(2020, 2026)}>2020 → 2026</button>
          <button className={before.year === 2023 && after.year === 2026 ? 'active' : ''} onClick={() => choosePair(2023, 2026)}>2023 → 2026</button>
        </div>
        <label>
          <span>ภาพหลัง</span>
          <select value={after.year} onChange={(event) => setAfterYear(Number(event.target.value))}>
            {scenes.map((scene) => (
              <option key={scene.year} value={scene.year} disabled={scene.year <= before.year}>
                {scene.year} · {scene.waterline_accepted ? 'คุมระดับน้ำ' : 'บริบทภาพ'}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="spectral-view-tabs">
        {(Object.keys(views) as ViewKey[]).map((key) => (
          <button key={key} className={view === key ? 'active' : ''} onClick={() => setView(key)}>
            <strong>{views[key].label_th}</strong><small>{views[key].description_th}</small>
          </button>
        ))}
      </div>

      <div
        className="spectral-swipe-stage"
        role="slider"
        tabIndex={0}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={split}
        aria-label={`เปรียบเทียบภาพ ${currentMode.label_th} ปี ${before.year} และ ${after.year}`}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onKeyDown={onKeyDown}
      >
        <img src={sceneImage(after, view, mode)} alt={`${currentMode.label_th} ปี ${after.year}`} draggable={false} />
        <img
          className="before"
          src={sceneImage(before, view, mode)}
          alt={`${currentMode.label_th} ปี ${before.year}`}
          draggable={false}
          style={{ clipPath: `inset(0 ${100 - split}% 0 0)` }}
        />
        <div className="spectral-divider" style={{ left: `${split}%` }}><span>↔</span></div>
        <div className="spectral-year-label before-label"><span>ก่อน</span><strong>{before.year}</strong><small>{before.date}</small></div>
        <div className="spectral-year-label after-label"><span>หลัง</span><strong>{after.year}</strong><small>{after.date}</small></div>
        <div className="spectral-location-note">กรอบเหลือง = พื้นที่ scene วิเคราะห์ · เส้นเหลือง = ขอบแปลง</div>
      </div>

      <div className="spectral-scene-meta">
        {[before, after].map((scene, index) => (
          <article key={`${scene.year}-${scene.scene_id}`} className={scene.waterline_accepted ? 'accepted' : 'context-only'}>
            <span>{index === 0 ? 'ภาพก่อน' : 'ภาพหลัง'}</span>
            <strong>{scene.year}<small>{scene.date}</small></strong>
            <p>{scene.tide_level_m_msl == null ? 'ไม่มีระดับน้ำสำหรับ Waterline' : `${scene.tide_level_m_msl.toFixed(3)} m MSL`}</p>
            <em>{scene.waterline_accepted ? 'ใช้ Waterline screening ได้' : 'ใช้ดูบริบท/ขอบพืชเท่านั้น'}</em>
          </article>
        ))}
        <div className={`spectral-tide-gap ${tideGap != null && tideGap <= 0.4 ? 'accepted' : 'review'}`}>
          <span>ต่างระดับน้ำ</span><strong>{tideGap == null ? '—' : tideGap.toFixed(3)}</strong><small>m MSL</small>
        </div>
      </div>

      <div className="spectral-source-note">
        <p><strong>พื้นหลัง:</strong> annual January–April Sentinel-2 composite ใช้เพื่อบอกตำแหน่ง ไม่ใช้แทน Waterline ที่คัดระดับน้ำ</p>
        <p><strong>กรอบวิเคราะห์:</strong> exact selected scene ของปีนั้น แสดง RGB / False colour / NDVI / MNDWI / SWIR จากแถบภาพเดียวกัน</p>
      </div>
    </section>
  )
}

function PeriodPanel({ title, subtitle, period }: { title: string; subtitle: string; period: PeriodMetrics }) {
  const values = periodCounts(period)
  const total = Math.max(period.classified_transect_count, 1)
  return (
    <article className="spectral-period-panel">
      <header><div><span>{subtitle}</span><h3>{title}</h3></div><strong>{period.classified_transect_count}<small>classified transects</small></strong></header>
      <div className="spectral-period-bar">
        <i className="landward" style={{ flex: Math.max(values.landward, 0.2) }} />
        <i className="within" style={{ flex: Math.max(values.within, 0.2) }} />
        <i className="seaward" style={{ flex: Math.max(values.seaward, 0.2) }} />
      </div>
      <div className="spectral-period-stats">
        <div className="landward"><strong>{values.landward}</strong><span>เข้าฝั่ง &gt;20 ม.</span><small>{percent(values.landward, total)}</small></div>
        <div><strong>{values.within}</strong><span>ภายใน ±20 ม.</span><small>{percent(values.within, total)}</small></div>
        <div className="seaward"><strong>{values.seaward}</strong><span>ออกทะเล &gt;20 ม.</span><small>{percent(values.seaward, total)}</small></div>
      </div>
      <dl><div><dt>Median NSM</dt><dd>{signed(period.median_nsm_m)} ม.</dd></div><div><dt>Median LRR</dt><dd>{signed(period.median_lrr_m_per_year)} ม./ปี</dd></div></dl>
    </article>
  )
}

function PlotExplorer({ plots }: { plots: PlotHistory[] }) {
  const coastal = useMemo(() => plots.filter((plot) => plot.treatment_transect_count > 0), [plots])
  const [plotId, setPlotId] = useState('97-STC')
  const selected = coastal.find((plot) => plot.plot_id === plotId) ?? coastal[0]
  if (!selected) return null
  const historical = selected.waterline.historical_class_counts.APPARENT_LANDWARD ?? 0
  const recent = selected.waterline.recent_class_counts.APPARENT_LANDWARD ?? 0

  return (
    <section className="spectral-card spectral-plot-explorer">
      <header className="spectral-section-heading"><div><span>RESULT BY PLOT</span><h2>ดูจุดที่เคยมีสัญญาณถอยเข้าฝั่ง</h2></div><p>จำนวนแนวลดลงไม่ได้แปลว่าการปลูกเป็นสาเหตุ</p></header>
      <div className="spectral-plot-tabs">
        {coastal.map((plot) => (
          <button key={plot.plot_id} className={plot.plot_id === selected.plot_id ? 'active' : ''} onClick={() => setPlotId(plot.plot_id)}>
            <strong>{plot.plot_id}</strong>
            <small>{plot.waterline.historical_class_counts.APPARENT_LANDWARD ?? 0} → {plot.waterline.recent_class_counts.APPARENT_LANDWARD ?? 0}</small>
          </button>
        ))}
      </div>
      <div className="spectral-plot-result">
        <div><span>ก่อนปี 2023</span><strong>{historical}/{selected.treatment_transect_count}</strong><small>แนวเข้าฝั่งเกิน 20 ม.</small></div>
        <i>→</i>
        <div className="recent"><span>2023–2026</span><strong>{recent}/{selected.treatment_transect_count}</strong><small>แนวเข้าฝั่งเกิน 20 ม.</small></div>
        <article><strong>{historical > recent ? 'สัญญาณเข้าฝั่งลดลงในช่วงล่าสุด' : 'ยังไม่เห็นการลดลงชัดเจน'}</strong><p>Control {selected.candidate_control_count} แนวยังไม่ได้ตรวจโครงสร้างชายฝั่ง การขุดลอก การถม และประวัติปลูก</p></article>
      </div>
    </section>
  )
}

export default function PreplantingHistoryDashboardV2({ history, onOpenCurrent, onOpenDrone, onOpenProject, onOpenCoast }: Props) {
  const waterline = history.indicators.waterline
  const mangrove = history.indicators.mangrove_edge_proxy
  const before = periodCounts(waterline.historical)
  const recent = periodCounts(waterline.recent)
  const fractionChange = (
    history.answer_to_preplanting_question.historical_apparent_landward_fraction
    - history.answer_to_preplanting_question.recent_apparent_landward_fraction
  ) * 100

  return (
    <main className="spectral-shell">
      <nav className="spectral-nav">
        <div><span>สมุทรสงคราม</span><strong>Coastal History Evidence</strong></div>
        <div><button className="active">หลักฐานย้อนหลัง</button><button onClick={onOpenCurrent}>ผล 2023–2026</button><button onClick={onOpenDrone}>ภาพโดรน HR</button><button onClick={onOpenProject}>รายงาน 9 แปลง</button><button onClick={onOpenCoast}>แผนที่ 10 ปี</button></div>
      </nav>

      <header className="spectral-hero">
        <div>
          <span>PRE-PLANTING CONTEXT · SENTINEL-2 · 2017–2026</span>
          <h1>ก่อนปี 2023<br /><em>ชายฝั่งเคยถอยหรือไม่?</em></h1>
          <p>ดูภาพย้อนหลังพร้อมพื้นหลังบอกตำแหน่ง และสลับ RGB, False colour, NDVI, MNDWI และ SWIR ให้ตรงกับคำถามเรื่องขอบพืช น้ำ และพื้นที่ชื้น</p>
          <a href="#history-compare">เปิดสไลเดอร์หลายสี</a>
        </div>
        <article>
          <span>{history.evidence_level.replaceAll('_', ' ')}</span>
          <h2>พบสัญญาณก่อนปี 2023<br /><em>มากกว่าช่วงล่าสุดบางตำแหน่ง</em></h2>
          <p>{history.answer_to_preplanting_question.headline_th}</p>
          <strong>ยังไม่พิสูจน์ว่าแนวโน้มดีขึ้นเพราะการปลูก</strong>
          <small>EROSION EFFECT: {history.erosion_effect_conclusion}</small>
        </article>
      </header>

      <section className="spectral-kpis">
        <article><span>ช่วงภาพย้อนหลัง</span><strong>2017–2026</strong><small>10 annual Sentinel-2 records</small></article>
        <article><span>Waterline คุมระดับน้ำ</span><strong>{history.scene_selection.accepted_waterline_years.length}</strong><small>{history.scene_selection.accepted_waterline_years.join(', ')}</small></article>
        <article className="landward"><span>ก่อนปี 2023 เข้าฝั่ง</span><strong>{before.landward}</strong><small>{percent(before.landward, waterline.historical.classified_transect_count)}</small></article>
        <article className="seaward"><span>2023–2026 เข้าฝั่ง</span><strong>{recent.landward}</strong><small>{percent(recent.landward, waterline.recent.classified_transect_count)}</small></article>
        <article><span>สัดส่วนเข้าฝั่งลดลง</span><strong>{fractionChange.toFixed(1)}</strong><small>percentage points · screening</small></article>
        <article><span>Transects หน้าแปลง</span><strong>{history.transects.treatment_count}</strong><small>91–98 STC</small></article>
      </section>

      <SpectralCompare history={history} />

      <section className="spectral-period-grid">
        <PeriodPanel title="ก่อนช่วงดำเนินการ" subtitle={history.periods.historical_preplanting.label_th} period={waterline.historical} />
        <div className="spectral-change-panel"><span>แนวเข้าฝั่ง</span><strong>{before.landward} → {recent.landward}</strong><small>ลดลง {fractionChange.toFixed(1)} จุดร้อยละ</small><em>ยังไม่ใช่ causal effect</em></div>
        <PeriodPanel title="ช่วงติดตามล่าสุด" subtitle={history.periods.recent_monitoring.label_th} period={waterline.recent} />
      </section>

      <section className="spectral-card spectral-proxy">
        <header className="spectral-section-heading"><div><span>VEGETATION EDGE PROXY</span><h2>NDVI และ False colour ช่วยอ่านขอบพืช</h2></div><p>แต่ยังไม่ใช่ขอบป่าที่ตรวจรับด้วยโดรน</p></header>
        <div><article><span>2017–2023</span><strong>{signed(mangrove.historical.median_nsm_m)} ม.</strong><small>Median NSM · LRR {signed(mangrove.historical.median_lrr_m_per_year)} ม./ปี</small></article><i>→</i><article className="recent"><span>2023–2026</span><strong>{signed(mangrove.recent.median_nsm_m)} ม.</strong><small>Median NSM · LRR {signed(mangrove.recent.median_lrr_m_per_year)} ม./ปี</small></article></div>
        <p>NDVI, MNDWI และ SWIR เป็นข้อมูลเชิงสเปกตรัม ไม่ใช่ข้อมูลตะกอน คลื่น หรือความสูงพื้นดิน และไม่ควรใช้แทนการสำรวจโดรน</p>
      </section>

      <PlotExplorer plots={history.per_plot} />

      <section className="spectral-card spectral-claim-guard">
        <div><span>ข้อความที่ใช้ได้</span><p>{history.allowed_claim_th}</p></div>
        <div><span>ข้อความที่ยังใช้ไม่ได้</span><p>“ตั้งแต่ปลูกแล้วการกัดเซาะหยุดลง” เพราะวันปลูกจริงยังไม่ยืนยันและ candidate controls ยังไม่ได้ตรวจปัจจัยรบกวน</p></div>
      </section>

      <details className="spectral-details">
        <summary>ข้อจำกัดและไฟล์ตรวจสอบ</summary>
        <div><ul>{history.limitations.map((item) => <li key={item}>{item}</li>)}</ul><nav><a href="data/project_preplanting_history/summary.json" target="_blank" rel="noreferrer">Summary JSON</a><a href="data/project_preplanting_history/treatment_transects_periods.geojson" target="_blank" rel="noreferrer">Transect GeoJSON</a></nav></div>
      </details>

      <footer className="spectral-footer"><strong>{history.evidence_level}</strong><p>{history.periods.intervention_note}</p><small>Generated {new Date(history.generated_at_utc).toLocaleString('th-TH')}</small></footer>
    </main>
  )
}
