import {
  useMemo,
  useState,
  type KeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from 'react'
import type { TideAwareIndicatorResult, TideAwareSummary } from './types'
import './tideAwareOverview.css'

type Props = {
  summary: TideAwareSummary
  onOpenProject: () => void
  onOpenCoast: () => void
}

type TideScene = TideAwareSummary['waterline_scene_selection']['selected_scenes'][number]
type PlotResult = TideAwareSummary['per_plot'][number]

type CompareProps = {
  scenes: TideScene[]
}

const COASTAL_PLOTS = ['91-STC', '92-STC', '93-STC', '94-STC', '95-STC', '96-STC', '97-STC', '98-STC']

function signed(value: number | null, digits = 1): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${value >= 0 ? '+' : ''}${value.toFixed(digits)}`
}

function percent(value: number, total: number): string {
  if (!total) return '0%'
  return `${Math.round((value / total) * 100)}%`
}

function sourceLabel(source: string): string {
  return source === 'official_hourly_prediction'
    ? 'ตารางรายชั่วโมงทางการ'
    : 'ค่าประมาณจากจุดน้ำขึ้น–ลงที่ตรวจเทียบแล้ว'
}

function sceneRole(year: number): string {
  if (year === 2023) return 'ก่อนดำเนินการ'
  if (year === 2024) return 'ช่วงดำเนินการ*'
  return 'หลังดำเนินการ'
}

function sceneImage(scene: TideScene): string {
  return `data/project_tide_aware/imagery/${scene.year}_selected.webp`
}

function indicatorCounts(result: TideAwareIndicatorResult) {
  return {
    inland: result.class_counts.APPARENT_LANDWARD ?? 0,
    within: result.class_counts.WITHIN_20M ?? 0,
    seaward: result.class_counts.APPARENT_SEAWARD ?? 0,
  }
}

function movementLabel(value: number | null): string {
  if (value == null) return 'ไม่มีข้อมูล'
  if (value > 20) return 'ปรากฏเคลื่อนออกทะเลเกิน 20 ม.'
  if (value < -20) return 'ปรากฏเคลื่อนเข้าฝั่งเกิน 20 ม.'
  return 'อยู่ในช่วงความละเอียด ±20 ม.'
}

function comparisonLabel(value: number | null): string {
  if (value == null) return 'ยังเปรียบเทียบไม่ได้'
  if (value > 10) return 'หน้าแปลงมีสัญญาณดีกว่า control เบื้องต้น'
  if (value < -10) return 'หน้าแปลงมีสัญญาณน้อยกว่า control เบื้องต้น'
  return 'ใกล้เคียง control เบื้องต้น'
}

function scopeLabel(scope: string): string {
  if (scope === 'INCLUDED_IN_COASTAL_SCREENING') return 'รวมในการคัดกรองชายฝั่ง'
  if (scope === 'EXCLUDED_FROM_COASTAL_SCREENING') return 'แยกจากการวิเคราะห์ชายฝั่งทะเล'
  return 'ต้องตรวจ geometry'
}

function TideMatchChart({ scenes, target }: { scenes: TideScene[]; target: number }) {
  const values = scenes.map((scene) => scene.tide_level_m_msl)
  const lower = Math.min(...values, target) - 0.08
  const upper = Math.max(...values, target) + 0.08
  const position = (value: number) => ((value - lower) / Math.max(upper - lower, 0.001)) * 100

  return (
    <section className="evidence-card tide-match-card" aria-labelledby="tide-match-heading">
      <div className="section-title-row">
        <div>
          <span>ระดับน้ำของภาพที่เลือก</span>
          <h2 id="tide-match-heading">สี่ปีอยู่ใกล้กันเพียงใด</h2>
        </div>
        <strong>{(upper - lower - 0.16).toFixed(3)} ม. spread</strong>
      </div>
      <div className="tide-axis" aria-label="กราฟระดับน้ำของภาพดาวเทียมแต่ละปี">
        <div className="tide-axis-line" />
        <div className="tide-target" style={{ left: `${position(target)}%` }}>
          <i />
          <span>เป้าหมาย {target.toFixed(3)} m MSL</span>
        </div>
        {scenes.map((scene, index) => (
          <div
            className={`tide-point source-${scene.tide_source_tier}`}
            key={scene.year}
            style={{ left: `${position(scene.tide_level_m_msl)}%`, top: `${38 + (index % 2) * 38}px` }}
          >
            <i />
            <strong>{scene.year}</strong>
            <span>{scene.tide_level_m_msl.toFixed(3)}</span>
          </div>
        ))}
      </div>
      <div className="tide-axis-labels">
        <span>{lower.toFixed(2)} m MSL</span>
        <span>{upper.toFixed(2)} m MSL</span>
      </div>
      <p>
        ปี 2026 ใช้ตารางรายชั่วโมงทางการ ส่วนปี 2023–2025 เป็นค่าประมาณระหว่างจุดน้ำขึ้น–น้ำลงที่ตรวจเทียบแล้ว
        จึงใช้เพื่อลดความต่างของระดับน้ำ ไม่ใช่การปรับ shoreline ให้เป็นระดับเดียวกันอย่างสมบูรณ์
      </p>
    </section>
  )
}

function SatelliteCompare({ scenes }: CompareProps) {
  const orderedScenes = useMemo(
    () => [...scenes].sort((left, right) => left.year - right.year),
    [scenes],
  )
  const firstYear = orderedScenes[0]?.year ?? 2023
  const lastYear = orderedScenes[orderedScenes.length - 1]?.year ?? 2026
  const [beforeYear, setBeforeYear] = useState(firstYear)
  const [afterYear, setAfterYear] = useState(lastYear)
  const [split, setSplit] = useState(50)
  const [focusCoast, setFocusCoast] = useState(true)

  const before = orderedScenes.find((scene) => scene.year === beforeYear)
  const after = orderedScenes.find((scene) => scene.year === afterYear)

  if (!before || !after) return <div className="compare-empty">ไม่พบภาพดาวเทียมสำหรับเปรียบเทียบ</div>

  const tideDifference = Math.abs(after.tide_level_m_msl - before.tide_level_m_msl)

  const setPair = (beforeValue: number, afterValue: number) => {
    setBeforeYear(beforeValue)
    setAfterYear(afterValue)
    setSplit(50)
  }

  const changeBefore = (year: number) => {
    setBeforeYear(year)
    if (year >= afterYear) {
      const next = orderedScenes.find((scene) => scene.year > year)
      if (next) setAfterYear(next.year)
    }
  }

  const changeAfter = (year: number) => {
    setAfterYear(year)
    if (year <= beforeYear) {
      const previous = [...orderedScenes].reverse().find((scene) => scene.year < year)
      if (previous) setBeforeYear(previous.year)
    }
  }

  const updateSplit = (clientX: number, element: HTMLDivElement) => {
    const bounds = element.getBoundingClientRect()
    const next = ((clientX - bounds.left) / Math.max(bounds.width, 1)) * 100
    setSplit(Math.max(0, Math.min(100, Math.round(next))))
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
    if (event.key === 'ArrowLeft') {
      event.preventDefault()
      setSplit((value) => Math.max(0, value - 2))
    }
    if (event.key === 'ArrowRight') {
      event.preventDefault()
      setSplit((value) => Math.min(100, value + 2))
    }
    if (event.key === 'Home') setSplit(0)
    if (event.key === 'End') setSplit(100)
  }

  return (
    <section className="evidence-card compare-card" id="compare" aria-labelledby="compare-heading">
      <div className="section-title-row compare-title-row">
        <div>
          <span>ภาพดาวเทียมจริง · Sentinel-2</span>
          <h2 id="compare-heading">ลากเส้นเพื่อเทียบก่อน–หลัง</h2>
        </div>
        <div className={`tide-gap-badge ${tideDifference <= 0.4 ? 'accepted' : 'review'}`}>
          <span>ต่างระดับน้ำ</span>
          <strong>{tideDifference.toFixed(3)} ม.</strong>
          <small>{tideDifference <= 0.4 ? 'ผ่านเกณฑ์ screening' : 'ควรทบทวน'}</small>
        </div>
      </div>

      <div className="compare-quick-pairs" aria-label="คู่ปีแนะนำ">
        <span>คู่เปรียบเทียบ:</span>
        <button type="button" className={beforeYear === 2023 && afterYear === 2026 ? 'active' : ''} onClick={() => setPair(2023, 2026)}>2023 → 2026</button>
        <button type="button" className={beforeYear === 2023 && afterYear === 2024 ? 'active' : ''} onClick={() => setPair(2023, 2024)}>ก่อน → ช่วงดำเนินการ</button>
        <button type="button" className={beforeYear === 2024 && afterYear === 2026 ? 'active' : ''} onClick={() => setPair(2024, 2026)}>ดำเนินการ → ล่าสุด</button>
      </div>

      <div className="compare-toolbar">
        <label>
          <span>ก่อน / Before</span>
          <select value={beforeYear} onChange={(event) => changeBefore(Number(event.target.value))}>
            {orderedScenes.map((scene) => (
              <option key={scene.year} value={scene.year} disabled={scene.year >= afterYear}>
                {scene.year} · {sceneRole(scene.year)}
              </option>
            ))}
          </select>
        </label>

        <div className="compare-focus-toggle" aria-label="เลือกบริเวณภาพ">
          <button type="button" className={focusCoast ? 'active' : ''} onClick={() => setFocusCoast(true)}>โฟกัสแปลงชายฝั่ง</button>
          <button type="button" className={!focusCoast ? 'active' : ''} onClick={() => setFocusCoast(false)}>ภาพรวม 9 แปลง</button>
        </div>

        <label>
          <span>หลัง / After</span>
          <select value={afterYear} onChange={(event) => changeAfter(Number(event.target.value))}>
            {orderedScenes.map((scene) => (
              <option key={scene.year} value={scene.year} disabled={scene.year <= beforeYear}>
                {scene.year} · {sceneRole(scene.year)}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div
        className={`compare-stage ${focusCoast ? 'is-coast-focus' : 'is-overview'}`}
        role="slider"
        tabIndex={0}
        aria-label={`เปิดภาพปี ${before.year} เทียบปี ${after.year}`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={split}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onKeyDown={onKeyDown}
      >
        <img className="compare-layer compare-after" src={sceneImage(after)} alt={`Sentinel-2 ปี ${after.year}`} draggable={false} />
        <img
          className="compare-layer compare-before"
          src={sceneImage(before)}
          alt={`Sentinel-2 ปี ${before.year}`}
          draggable={false}
          style={{ clipPath: `inset(0 ${100 - split}% 0 0)` }}
        />
        <div className="compare-divider" style={{ left: `${split}%` }}><i>↔</i></div>
        <div className="compare-year-label before"><span>ก่อน</span><strong>{before.year}</strong><small>{before.date}</small></div>
        <div className="compare-year-label after"><span>หลัง</span><strong>{after.year}</strong><small>{after.date}</small></div>
        <div className="compare-location-label coast">บริเวณแปลง 91–98 STC</div>
        {!focusCoast && <div className="compare-location-label inland">87-VSD · แยกวิเคราะห์ขอบคลอง</div>}
      </div>

      <div className="compare-range-row">
        <span>ก่อน {before.year}</span>
        <input
          type="range"
          min="0"
          max="100"
          value={split}
          aria-label="ตำแหน่งเส้นแบ่งภาพก่อนหลัง"
          onChange={(event) => setSplit(Number(event.target.value))}
        />
        <span>หลัง {after.year}</span>
        <button type="button" onClick={() => setSplit(50)}>กึ่งกลาง</button>
      </div>

      <div className="compare-metadata">
        <article>
          <span>{sceneRole(before.year)}</span>
          <strong>{before.date}</strong>
          <small>{before.tide_level_m_msl.toFixed(3)} m MSL</small>
          <p>{sourceLabel(before.tide_source_tier)}</p>
        </article>
        <article className="compare-read-note">
          <strong>ควรดูขอบป่าด้านทะเล</strong>
          <p>ไม่ควรใช้สีของน้ำหรือความเขียวเพียงอย่างเดียวตัดสินการกัดเซาะ</p>
        </article>
        <article className="after">
          <span>{sceneRole(after.year)}</span>
          <strong>{after.date}</strong>
          <small>{after.tide_level_m_msl.toFixed(3)} m MSL</small>
          <p>{sourceLabel(after.tide_source_tier)}</p>
        </article>
      </div>
    </section>
  )
}

function PlotExplorer({ summary }: { summary: TideAwareSummary }) {
  const defaultPlot = useMemo(() => {
    const screenable = summary.per_plot.filter((plot) => COASTAL_PLOTS.includes(plot.plot_id))
    return screenable.reduce((selected, plot) => {
      const current = Math.abs(plot.mangrove_edge_proxy.screening_difference_m ?? 0)
      const previous = Math.abs(selected.mangrove_edge_proxy.screening_difference_m ?? 0)
      return current > previous ? plot : selected
    }, screenable[0] ?? summary.per_plot[0])
  }, [summary.per_plot])
  const [selectedPlotId, setSelectedPlotId] = useState(defaultPlot?.plot_id ?? '91-STC')
  const selected = summary.per_plot.find((plot) => plot.plot_id === selectedPlotId) ?? defaultPlot

  if (!selected) return null

  const excluded = selected.coastal_eligibility.coastal_erosion_scope === 'EXCLUDED_FROM_COASTAL_SCREENING'

  return (
    <section className="evidence-card plot-explorer" id="plots" aria-labelledby="plot-heading">
      <div className="section-title-row">
        <div>
          <span>ผลรายแปลง</span>
          <h2 id="plot-heading">เลือกแปลงเพื่อดูหลักฐานที่มี</h2>
        </div>
        <small>ค่าทั้งหมดยังเป็น LOW-confidence screening</small>
      </div>

      <div className="plot-tabs" role="tablist" aria-label="เลือกแปลงปลูก">
        {summary.per_plot.map((plot) => (
          <button
            key={plot.plot_id}
            type="button"
            role="tab"
            aria-selected={selectedPlotId === plot.plot_id}
            className={`${selectedPlotId === plot.plot_id ? 'active' : ''} ${plot.plot_id === '87-VSD' ? 'inland' : ''}`}
            onClick={() => setSelectedPlotId(plot.plot_id)}
          >
            {plot.plot_id}
          </button>
        ))}
      </div>

      <div className={`plot-evidence-panel ${excluded ? 'excluded' : ''}`}>
        <header>
          <div>
            <span>{scopeLabel(selected.coastal_eligibility.coastal_erosion_scope)}</span>
            <h3>{selected.plot_id}</h3>
            <p>{selected.official_participating_area_rai.toFixed(1)} ไร่</p>
          </div>
          <div className="plot-status-badge">{excluded ? 'BANK / CANAL EDGE' : 'COASTAL SCREENING'}</div>
        </header>

        {excluded ? (
          <div className="excluded-message">
            <strong>แปลงนี้ไม่ควรรวมในข้อสรุปการกัดเซาะชายฝั่งทะเล</strong>
            <p>
              อยู่ห่าง waterline ที่สกัดได้ประมาณ {selected.coastal_eligibility.distance_to_2026_waterline_m.toFixed(0)} เมตร
              จึงควรใช้โดรนหรือการเดินสำรวจติดตาม BANK_EDGE หรือขอบคลองแยกต่างหาก
            </p>
          </div>
        ) : (
          <>
            <div className="plot-metric-grid">
              <article>
                <span>Waterline NSM</span>
                <strong>{signed(selected.waterline.median_nsm_2023_2026_m)} ม.</strong>
                <small>{movementLabel(selected.waterline.median_nsm_2023_2026_m)}</small>
              </article>
              <article>
                <span>ขอบพืช NSM</span>
                <strong>{signed(selected.mangrove_edge_proxy.median_nsm_2023_2026_m)} ม.</strong>
                <small>{movementLabel(selected.mangrove_edge_proxy.median_nsm_2023_2026_m)}</small>
              </article>
              <article>
                <span>ขอบพืชเทียบ control</span>
                <strong>{signed(selected.mangrove_edge_proxy.screening_difference_m)} ม.</strong>
                <small>{comparisonLabel(selected.mangrove_edge_proxy.screening_difference_m)}</small>
              </article>
              <article>
                <span>แนววิเคราะห์</span>
                <strong>{selected.coastal_eligibility.treatment_transect_count}</strong>
                <small>transects · {selected.waterline.candidate_control_count} controls</small>
              </article>
            </div>
            <div className="plot-interpretation">
              <strong>การอ่านผลที่เหมาะสม</strong>
              <p>
                {movementLabel(selected.waterline.median_nsm_2023_2026_m)} ขณะที่ {comparisonLabel(selected.mangrove_edge_proxy.screening_difference_m)}
                แต่ controls ยังไม่ได้ตรวจโครงสร้างชายฝั่ง การขุดลอก การถม และประวัติปลูก จึงยังไม่ใช่ผลเชิงเหตุ–ผล
              </p>
            </div>
          </>
        )}
      </div>

      <details className="full-table-details">
        <summary>เปิดตารางครบทุกแปลง</summary>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>แปลง</th>
                <th>ขอบเขต</th>
                <th>Transects</th>
                <th>Waterline NSM</th>
                <th>ขอบพืช NSM</th>
                <th>ขอบพืชเทียบ control</th>
              </tr>
            </thead>
            <tbody>
              {summary.per_plot.map((plot) => (
                <tr key={plot.plot_id}>
                  <td><strong>{plot.plot_id}</strong></td>
                  <td>{scopeLabel(plot.coastal_eligibility.coastal_erosion_scope)}</td>
                  <td>{plot.coastal_eligibility.treatment_transect_count}</td>
                  <td>{signed(plot.waterline.median_nsm_2023_2026_m)} ม.</td>
                  <td>{signed(plot.mangrove_edge_proxy.median_nsm_2023_2026_m)} ม.</td>
                  <td>{signed(plot.mangrove_edge_proxy.screening_difference_m)} ม.</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  )
}

function SceneGallery({ scenes }: { scenes: TideScene[] }) {
  return (
    <section className="evidence-card scene-gallery" aria-labelledby="scene-gallery-heading">
      <div className="section-title-row">
        <div>
          <span>ภาพที่ใช้จริง</span>
          <h2 id="scene-gallery-heading">ตรวจสอบภาพทั้งสี่ปี</h2>
        </div>
        <small>คลิกเพื่อเปิดไฟล์ภาพเต็ม</small>
      </div>
      <div className="scene-grid">
        {scenes.map((scene) => (
          <a key={scene.year} href={sceneImage(scene)} target="_blank" rel="noreferrer">
            <div className="scene-image-wrap">
              <img src={sceneImage(scene)} alt={`Sentinel-2 สมุทรสงคราม ปี ${scene.year}`} loading="lazy" />
              <span>{scene.year}</span>
            </div>
            <div>
              <strong>{sceneRole(scene.year)}</strong>
              <p>{scene.date}</p>
              <small>{scene.tide_level_m_msl.toFixed(3)} m MSL</small>
            </div>
          </a>
        ))}
      </div>
    </section>
  )
}

export default function TideAwareOverview({ summary, onOpenProject, onOpenCoast }: Props) {
  const waterline = summary.indicators.waterline
  const mangrove = summary.indicators.mangrove_edge_proxy
  const waterlineCounts = indicatorCounts(waterline)
  const withinShare = percent(waterlineCounts.within, waterline.transect_count)
  const inlandShare = percent(waterlineCounts.inland, waterline.transect_count)
  const seawardShare = percent(waterlineCounts.seaward, waterline.transect_count)
  const vegetationAreaChange = mangrove.area_ha_by_year['2026'] - mangrove.area_ha_by_year['2023']

  return (
    <main className="report-shell evidence-v2">
      <nav className="report-nav evidence-nav">
        <div><span>สมุทรสงคราม</span><strong>Coastal Evidence</strong></div>
        <div className="view-tabs" role="tablist" aria-label="เลือกมุมมอง">
          <button role="tab" aria-selected="false" onClick={onOpenProject}>รายงาน 9 แปลง</button>
          <button className="active" role="tab" aria-selected="true">ภาพก่อน–หลัง</button>
          <button role="tab" aria-selected="false" onClick={onOpenCoast}>แผนที่ 10 ปี</button>
        </div>
      </nav>

      <header className="evidence-hero">
        <div className="evidence-hero-copy">
          <span className="hero-eyebrow">SENTINEL-2 · TIDE-AWARE SCREENING · 2023–2026</span>
          <h1>ชายฝั่งหน้าแปลง<br /><em>เปลี่ยนอย่างไรจากข้อมูลที่มี</em></h1>
          <p>
            เปรียบเทียบภาพดาวเทียมจริงที่คัดให้ระดับน้ำใกล้กัน แล้วแยกสิ่งที่ “พบ” ออกจากสิ่งที่ “ยังยืนยันไม่ได้”
            เพื่อไม่ให้ภาพก่อน–หลังถูกใช้เกินกว่าหลักฐาน
          </p>
          <div className="hero-actions">
            <a href="#compare">ดูภาพก่อน–หลัง</a>
            <a href="#plots" className="secondary">ดูผลรายแปลง</a>
            <a href="#method" className="text-link">วิธีและข้อจำกัด</a>
          </div>
        </div>
        <aside className="evidence-verdict">
          <span className="evidence-level">{summary.evidence_level.replaceAll('_', ' ')}</span>
          <strong>ยังไม่พิสูจน์ว่า<br />การปลูกลดการกัดเซาะ</strong>
          <p>แต่ข้อมูลสนับสนุนว่าแนวชายฝั่งส่วนใหญ่ยังไม่แสดงการถอยร่นขนาดใหญ่ในช่วงที่ศึกษา</p>
          <div><i />EROSION EFFECT: {summary.erosion_effect_conclusion}</div>
        </aside>
      </header>

      <section className="executive-findings" aria-label="ข้อค้นพบหลัก">
        <article className="finding-primary">
          <span>ข้อสรุปที่พูดได้ตอนนี้</span>
          <strong>ไม่พบการถอยร่นขนาดใหญ่เป็นวงกว้าง</strong>
          <p>{waterlineCounts.within} จาก {waterline.transect_count} แนว หรือ {withinShare} อยู่ภายในช่วงความละเอียด ±20 เมตร</p>
        </article>
        <article>
          <span>ปรากฏเข้าฝั่ง</span>
          <strong>{waterlineCounts.inland}</strong>
          <small>{inlandShare} ของ transects · จุดเฝ้าระวัง</small>
        </article>
        <article>
          <span>ปรากฏออกทะเล</span>
          <strong>{waterlineCounts.seaward}</strong>
          <small>{seawardShare} ของ transects · ยังอาจมีผลจากระดับน้ำ</small>
        </article>
        <article>
          <span>ขอบพืช spectral proxy</span>
          <strong>{signed(mangrove.median_nsm_2023_2026_m)} ม.</strong>
          <small>พื้นที่ proxy {signed(vegetationAreaChange, 0)} ha · ยังไม่ใช่พื้นที่ป่าที่ตรวจรับ</small>
        </article>
      </section>

      <section className="evidence-ladder" aria-label="ระดับหลักฐาน">
        <div className="ladder-heading">
          <span>เส้นทางสู่การเคลม</span>
          <strong>ตอนนี้อยู่ขั้นที่ 2 จาก 4</strong>
        </div>
        <ol>
          <li className="done"><i>1</i><div><strong>ภาพดาวเทียมหลายปี</strong><span>มีข้อมูล 2023–2026</span></div></li>
          <li className="current"><i>2</i><div><strong>คัดภาพตามระดับน้ำ</strong><span>ทำแล้ว · spread {summary.waterline_scene_selection.tide_spread_m.toFixed(3)} ม.</span></div></li>
          <li><i>3</i><div><strong>ยืนยันด้วยโดรน/ภาคสนาม</strong><span>ยังขาดขอบป่าหรือขอบตลิ่งซ้ำ</span></div></li>
          <li><i>4</i><div><strong>ยืนยันผลเทียบ control</strong><span>controls ยังไม่ตรวจปัจจัยรบกวน</span></div></li>
        </ol>
      </section>

      <SatelliteCompare scenes={summary.waterline_scene_selection.selected_scenes} />

      <div className="evidence-two-column">
        <TideMatchChart
          scenes={summary.waterline_scene_selection.selected_scenes}
          target={summary.waterline_scene_selection.target_tide_m_msl}
        />
        <section className="evidence-card read-result-card" aria-labelledby="read-result-heading">
          <div className="section-title-row">
            <div>
              <span>การตีความ</span>
              <h2 id="read-result-heading">สิ่งที่พบ กับสิ่งที่ยังพูดไม่ได้</h2>
            </div>
          </div>
          <div className="known-unknown-grid">
            <article className="known">
              <strong>พบจากข้อมูล</strong>
              <ul>
                <li>Waterline ค่ากึ่งกลางทั้งโครงการประมาณ {signed(waterline.median_nsm_2023_2026_m)} เมตร</li>
                <li>{withinShare} ของแนววิเคราะห์อยู่ภายใน ±20 เมตร</li>
                <li>ขอบพืชมีสัญญาณออกทะเลในหลายช่วง</li>
                <li>8 แปลงสัมพันธ์กับแนวหน้าชายฝั่ง</li>
              </ul>
            </article>
            <article className="unknown">
              <strong>ยังพูดไม่ได้</strong>
              <ul>
                <li>การปลูกเป็นสาเหตุของการเปลี่ยนแปลง</li>
                <li>ขอบพืช +20 เมตรเท่ากับแผ่นดินงอกจริง</li>
                <li>ลดคลื่น ดักตะกอน หรือป้องกันพายุได้เท่าไร</li>
                <li>87-VSD ช่วยลดการกัดเซาะชายฝั่งทะเล</li>
              </ul>
            </article>
          </div>
        </section>
      </div>

      <PlotExplorer summary={summary} />
      <SceneGallery scenes={summary.waterline_scene_selection.selected_scenes} />

      <section className="evidence-card method-card" id="method" aria-labelledby="method-heading">
        <div className="section-title-row">
          <div>
            <span>ตรวจสอบย้อนกลับ</span>
            <h2 id="method-heading">วิธี ข้อมูล และข้อจำกัด</h2>
          </div>
          <div className="download-links">
            <a href="data/project_tide_aware/summary.json" download>Summary JSON</a>
            <a href="data/project_tide_aware/transect_metrics.csv" download>Transect CSV</a>
            <a href="data/project_tide_aware/candidate_controls.csv" download>Controls CSV</a>
          </div>
        </div>

        <div className="method-steps">
          <article><i>1</i><strong>ฤดูกาลเดียวกัน</strong><p>ใช้ภาพช่วงมกราคม–เมษายน เพื่อลดความต่างจากฤดูกาลและเมฆ</p></article>
          <article><i>2</i><strong>ระดับน้ำใกล้กัน</strong><p>เลือกหนึ่ง acquisition ต่อปีให้ระดับน้ำทำนายข้ามปีใกล้กันที่สุด</p></article>
          <article><i>3</i><strong>แยกตัวชี้วัด</strong><p>Waterline ใช้สนับสนุน ส่วนขอบพืชใช้เป็น primary screening</p></article>
          <article><i>4</i><strong>เทียบ candidate controls</strong><p>เลือก 3 แนวต่อแปลงจากระยะและ pretrend แต่ยังต้องตรวจภาคสนาม</p></article>
        </div>

        <details>
          <summary>ข้อมูลระดับน้ำและเส้นอ้างอิง</summary>
          <p>
            ใช้สถานีปากน้ำแม่กลอง เวลาไทย UTC+7 และแปลงค่าให้อยู่บนฐาน Mean Sea Level เดียวกัน
            ปี 2026 เป็นตารางรายชั่วโมงทางการ ส่วนปี 2023–2025 เป็นค่าประมาณจากจุดน้ำขึ้น–น้ำลงที่ตรวจเทียบกับปี 2026 แล้ว
            ลมและความกดอากาศอาจทำให้ระดับจริงต่างจากค่าทำนาย
          </p>
        </details>

        <details>
          <summary>ข้อจำกัดทั้งหมด</summary>
          <ul className="limitations-list">
            {summary.limitations.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </details>

        <details>
          <summary>นิยามตัวชี้วัด</summary>
          <dl className="definition-grid">
            <div><dt>WATERLINE</dt><dd>ขอบน้ำจาก MNDWI ของภาพหนึ่งวันต่อปีที่คัดตามระดับน้ำ ใช้เป็น supporting evidence</dd></div>
            <div><dt>MANGROVE_EDGE_PROXY</dt><dd>ขอบพืช NDVI ≥ 0.35 จาก composite ฤดูกาลเดียวกัน ยังไม่ใช่แผนที่ป่าชายเลนที่ผ่าน confusion matrix</dd></div>
            <div><dt>NSM</dt><dd>ระยะต่างระหว่างตำแหน่งปีแรกและปีล่าสุด ค่าบวกหมายถึงออกทะเล</dd></div>
            <div><dt>CONTROL</dt><dd>แนวชายฝั่งใกล้เคียงที่จับคู่เบื้องต้น ยังไม่ได้ยืนยันโครงสร้าง การขุดลอก การถม และประวัติปลูก</dd></div>
          </dl>
        </details>
      </section>

      <footer className="evidence-footer">
        <strong>Samut Songkhram Coastal Evidence</strong>
        <p>{summary.allowed_claim_th}</p>
        <span>Predicted-tide satellite screening · Not a surveyed, tide-normalized, causal, or engineering shoreline report.</span>
      </footer>
    </main>
  )
}
