import { useMemo, useState } from 'react'
import type { TideAwareIndicatorResult, TideAwareSummary } from './types'
import './tideAwareSwipe.css'

type Props = {
  summary: TideAwareSummary
  onOpenProject: () => void
  onOpenCoast: () => void
}

type TideScene = TideAwareSummary['waterline_scene_selection']['selected_scenes'][number]

type SatelliteSwipeProps = {
  scenes: TideScene[]
}

function signed(value: number | null, digits = 2): string {
  if (value == null) return '—'
  return `${value >= 0 ? '+' : ''}${value.toFixed(digits)}`
}

function valueOrDash(value: number | null, suffix = ''): string {
  return value == null ? '—' : `${value.toFixed(2)}${suffix}`
}

function scopeLabel(scope: string): string {
  if (scope === 'INCLUDED_IN_COASTAL_SCREENING') return 'วิเคราะห์ชายฝั่งได้'
  if (scope === 'EXCLUDED_FROM_COASTAL_SCREENING') return 'ไม่ใช่แนวหน้าชายฝั่ง'
  return 'ต้องตรวจ geometry'
}

function sourceLabel(source: string): string {
  return source === 'official_hourly_prediction'
    ? 'ตารางรายชั่วโมงทางการ'
    : 'จุดน้ำขึ้น–ลงที่ตรวจเทียบแล้ว'
}

function sceneRole(year: number): string {
  if (year === 2023) return 'ก่อนดำเนินการ'
  if (year === 2024) return 'ปีดำเนินการ*'
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

function SatelliteSwipe({ scenes }: SatelliteSwipeProps) {
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

  if (!before || !after) {
    return <div className="satellite-swipe-card">ไม่พบภาพดาวเทียมสำหรับเปรียบเทียบ</div>
  }

  const tideDifference = Math.abs(after.tide_level_m_msl - before.tide_level_m_msl)

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

  return (
    <div className="satellite-swipe-card">
      <div className="satellite-swipe-toolbar">
        <label>
          ก่อน / Before
          <select value={beforeYear} onChange={(event) => changeBefore(Number(event.target.value))}>
            {orderedScenes.map((scene) => (
              <option key={scene.year} value={scene.year} disabled={scene.year >= afterYear}>
                {scene.year} · {sceneRole(scene.year)}
              </option>
            ))}
          </select>
        </label>

        <div className="satellite-view-toggle" aria-label="เลือกระดับการซูมภาพ">
          <button
            type="button"
            className={focusCoast ? 'active' : ''}
            onClick={() => setFocusCoast(true)}
          >
            โฟกัส 91–98 STC
          </button>
          <button
            type="button"
            className={!focusCoast ? 'active' : ''}
            onClick={() => setFocusCoast(false)}
          >
            เต็มพื้นที่ 9 แปลง
          </button>
        </div>

        <label>
          หลัง / After
          <select value={afterYear} onChange={(event) => changeAfter(Number(event.target.value))}>
            {orderedScenes.map((scene) => (
              <option key={scene.year} value={scene.year} disabled={scene.year <= beforeYear}>
                {scene.year} · {sceneRole(scene.year)}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className={`satellite-swipe-stage ${focusCoast ? 'is-coast-focus' : 'is-overview'}`}>
        <img
          className="satellite-swipe-layer satellite-swipe-after"
          src={sceneImage(after)}
          alt={`ภาพดาวเทียม Sentinel-2 จริง ปี ${after.year} หลังการดำเนินการ`}
          draggable={false}
        />
        <img
          className="satellite-swipe-layer satellite-swipe-before"
          src={sceneImage(before)}
          alt={`ภาพดาวเทียม Sentinel-2 จริง ปี ${before.year} ก่อนการดำเนินการ`}
          draggable={false}
          style={{ clipPath: `inset(0 ${100 - split}% 0 0)` }}
        />
        <div className="satellite-swipe-divider" style={{ left: `${split}%` }} />
        <div className="satellite-swipe-label before">
          <span>ก่อน / Before</span>
          <strong>{before.year}</strong>
          <small>{before.date} · {before.tide_level_m_msl.toFixed(3)} m MSL</small>
        </div>
        <div className="satellite-swipe-label after">
          <span>หลัง / After</span>
          <strong>{after.year}</strong>
          <small>{after.date} · {after.tide_level_m_msl.toFixed(3)} m MSL</small>
        </div>
      </div>

      <div className="satellite-swipe-controls">
        <span>ลากเพื่อเปิดภาพก่อน</span>
        <input
          aria-label={`เปรียบเทียบภาพดาวเทียมปี ${before.year} และ ${after.year}`}
          type="range"
          min="0"
          max="100"
          value={split}
          onChange={(event) => setSplit(Number(event.target.value))}
        />
        <output>{split}%</output>
      </div>

      <div className="satellite-swipe-meta">
        <div className="satellite-scene-meta">
          <span>{sceneRole(before.year)}</span>
          <strong>{before.date}</strong>
          <small>{before.tide_level_m_msl.toFixed(3)} m MSL · {sourceLabel(before.tide_source_tier)}</small>
        </div>
        <div className="satellite-tide-gap">
          <span>ต่างระดับน้ำ</span>
          <strong>{tideDifference.toFixed(3)}</strong>
          <small>เมตร MSL</small>
        </div>
        <div className="satellite-scene-meta after">
          <span>{sceneRole(after.year)}</span>
          <strong>{after.date}</strong>
          <small>{after.tide_level_m_msl.toFixed(3)} m MSL · {sourceLabel(after.tide_source_tier)}</small>
        </div>
      </div>
      <p className="satellite-focus-note">
        โหมดโฟกัสขยายกลุ่มแปลง 91–98-STC บริเวณชายฝั่งด้านขวาบนของภาพ ส่วนโหมดเต็มพื้นที่จะแสดง 87-VSD ด้านซ้ายล่างด้วย ซึ่งระบบแยกออกจากการวิเคราะห์แนวหน้าชายฝั่ง
      </p>
    </div>
  )
}

export default function TideAwareDashboard({ summary, onOpenProject, onOpenCoast }: Props) {
  const waterline = summary.indicators.waterline
  const mangrove = summary.indicators.mangrove_edge_proxy
  const waterlineCounts = indicatorCounts(waterline)
  const mangroveCounts = indicatorCounts(mangrove)
  const vegetationAreaChange =
    mangrove.area_ha_by_year['2026'] - mangrove.area_ha_by_year['2023']
  const excluded87 = summary.per_plot.find((item) => item.plot_id === '87-VSD')

  return (
    <main className="report-shell">
      <nav className="report-nav">
        <div><span>สมุทรสงคราม</span><strong>Coastal Erosion Evidence</strong></div>
        <div className="view-tabs" role="tablist" aria-label="เลือกมุมมอง">
          <button role="tab" aria-selected="false" onClick={onOpenProject}>รายงาน 9 แปลง</button>
          <button className="active" role="tab" aria-selected="true">ภาพก่อน–หลัง</button>
          <button role="tab" aria-selected="false" onClick={onOpenCoast}>แผนที่ 10 ปี</button>
        </div>
      </nav>

      <header className="report-hero">
        <div className="report-hero-copy">
          <span className="report-kicker">REAL SATELLITE IMAGERY · TIDE-AWARE SCREENING · 2023–2026</span>
          <h1>เลื่อนภาพก่อน–หลัง<br /><em>เพื่ออ่านหลักฐานอย่างถูกวิธี</em></h1>
          <p>
            ใช้ภาพ Sentinel-2 จริงที่ระบบคัดให้ระดับน้ำทำนายใกล้กัน แยกขอบน้ำออกจากขอบพืช
            และอธิบายเฉพาะสิ่งที่ภาพกับตัวเลขรองรับ ไม่ใช้สีของน้ำหรือความเขียวเพียงอย่างเดียวเป็นข้อพิสูจน์
          </p>
        </div>
        <article className="verdict-card">
          <div className="verdict-status"><i />{summary.evidence_level.replaceAll('_', ' ')}</div>
          <strong>ยังไม่พิสูจน์<br />ว่าลดการกัดเซาะ</strong>
          <p>{summary.allowed_claim_th}</p>
          <span>EROSION EFFECT: {summary.erosion_effect_conclusion}</span>
        </article>
      </header>

      <section className="report-kpis" aria-label="ตัวชี้วัดสำคัญ">
        <article><span>แปลงที่วิเคราะห์ชายฝั่งได้</span><strong>{summary.coastal_eligibility.screenable_plot_count}</strong><small>{summary.coastal_eligibility.screenable_plot_ids.join(', ')}</small></article>
        <article className="caution"><span>แปลงที่แยกออก</span><strong>{summary.coastal_eligibility.excluded_plot_count}</strong><small>{summary.coastal_eligibility.excluded_plot_ids.join(', ')}</small></article>
        <article><span>Transects หน้าแปลง</span><strong>{summary.transects.treatment_count}</strong><small>จากทั้งหมด {summary.transects.total_count.toLocaleString()}</small></article>
        <article><span>Candidate controls</span><strong>{summary.controls.selected_count}</strong><small>{summary.controls.status.replaceAll('_', ' ')}</small></article>
        <article><span>ช่วงระดับน้ำที่เลือก</span><strong>{summary.waterline_scene_selection.tide_spread_m.toFixed(3)}</strong><small>เมตร MSL ระหว่าง 4 ปี</small></article>
        <article className="positive"><span>Waterline ใน ±20 ม.</span><strong>{waterlineCounts.within}/{waterline.transect_count}</strong><small>ใช้เป็นหลักฐานสนับสนุนเท่านั้น</small></article>
      </section>

      <section className="report-panel satellite-swipe-panel">
        <div className="report-panel-heading">
          <div><span>01 · BEFORE / AFTER SATELLITE SWIPE</span><h2>เปรียบเทียบภาพดาวเทียมจริงบนตำแหน่งเดียวกัน</h2></div>
          <p>ค่าเป้าหมาย {summary.waterline_scene_selection.target_tide_m_msl.toFixed(3)} m MSL · spread {summary.waterline_scene_selection.tide_spread_m.toFixed(3)} m</p>
        </div>

        <div className="satellite-swipe-layout">
          <SatelliteSwipe scenes={summary.waterline_scene_selection.selected_scenes} />

          <aside className="satellite-reading-guide" aria-label="คำแนะนำการอ่านภาพดาวเทียม">
            <header>
              <span>HOW TO READ THE IMAGE</span>
              <h3>ภาพนี้ควรดูอะไร และไม่ควรสรุปอะไร</h3>
            </header>
            <article>
              <span>1</span>
              <strong>ดูขอบป่าด้านทะเลก่อนสีของน้ำ</strong>
              <p>สีของน้ำเปลี่ยนได้จากตะกอนแขวนลอย แสง เมฆบาง และช่วงเวลาถ่าย จึงไม่ใช่หลักฐานการกัดเซาะโดยตรง</p>
            </article>
            <article>
              <span>2</span>
              <strong>ขอบน้ำส่วนใหญ่ยังอยู่ในช่วงความละเอียด</strong>
              <p>{waterlineCounts.within} จาก {waterline.transect_count} transects อยู่ภายใน ±20 เมตร และค่ากึ่งกลาง NSM เท่ากับ {signed(waterline.median_nsm_2023_2026_m)} เมตร</p>
            </article>
            <article>
              <span>3</span>
              <strong>ขอบพืชมีสัญญาณออกทะเล แต่ยังเป็น proxy</strong>
              <p>ค่ากึ่งกลาง mangrove-edge proxy เท่ากับ {signed(mangrove.median_nsm_2023_2026_m)} เมตร ต้องตรวจซ้ำด้วยโดรนหรือภาคสนามก่อนเรียกว่าแนวป่าขยายจริง</p>
            </article>
            <article>
              <span>4</span>
              <strong>ภาพก่อน–หลังยังไม่พิสูจน์สาเหตุ</strong>
              <p>ต้องตรวจพื้นที่ควบคุม โครงสร้างชายฝั่ง การขุดลอก การถม และวันปลูก ก่อนเชื่อมผลกับโครงการ</p>
            </article>
          </aside>
        </div>

        <div className="satellite-principles" aria-label="หลักการเปรียบเทียบภาพชายฝั่ง">
          <article><span>01</span><strong>ฤดูกาลเดียวกัน</strong><p>ใช้ภาพช่วงมกราคม–เมษายนเพื่อลดความต่างจากฤดูกาล เมฆ และสภาพพืช</p></article>
          <article><span>02</span><strong>ระดับน้ำใกล้กัน</strong><p>เลือกหนึ่ง acquisition ต่อปีให้ค่าระดับน้ำ MSL ข้ามปีใกล้กันที่สุด ไม่ใช้ภาพน้ำขึ้นกับน้ำลงมาเทียบตรง ๆ</p></article>
          <article><span>03</span><strong>แยกตัวชี้วัด</strong><p>Waterline ใช้สนับสนุน ส่วนขอบพืชด้านทะเลใช้เป็น primary screening แต่ยังไม่ใช่แผนที่ป่าที่ตรวจรับแล้ว</p></article>
          <article><span>04</span><strong>เทียบพื้นที่ควบคุม</strong><p>ผลหน้าแปลงต้องดีกว่าพื้นที่ใกล้เคียงที่มีแนวโน้มเดิมคล้ายกัน จึงค่อยพิจารณาผลของโครงการ</p></article>
        </div>

        <div className="tide-source-strip">
          <div><span>สถานีระดับน้ำ</span><strong>ปากน้ำแม่กลอง</strong><small>13°22′39″N · 99°59′34″E</small></div>
          <div><span>เส้นอ้างอิง</span><strong>Mean Sea Level</strong><small>เวลาไทย UTC+7 · LLW ต่ำกว่า MSL 2.14 ม.</small></div>
          <p>ระดับน้ำเป็นค่าทำนาย ไม่ใช่ค่าที่วัดตรงหน้าแปลง ลมและความกดอากาศอาจทำให้ระดับน้ำจริงสูงหรือต่ำกว่าค่าทำนาย จึงยังไม่แปลงความต่างระดับน้ำเป็นระยะทางแนวราบ</p>
        </div>
      </section>

      <section className="report-panel imagery-panel">
        <div className="report-panel-heading">
          <div><span>02 · COMPARABLE-TIDE SCENES</span><h2>ภาพทั้งสี่ปีที่ใช้ในการวิเคราะห์</h2></div>
          <p>Sentinel-2 true-color preview · คลิกเพื่อเปิดภาพเต็ม</p>
        </div>
        <div className="imagery-timeline">
          {summary.waterline_scene_selection.selected_scenes.map((scene) => (
            <figure key={scene.year}>
              <a
                className="satellite-image"
                href={sceneImage(scene)}
                target="_blank"
                rel="noreferrer"
                aria-label={`เปิดภาพ Sentinel-2 ที่คัดตามระดับน้ำ ปี ${scene.year}`}
              >
                <img
                  src={sceneImage(scene)}
                  alt={`ภาพดาวเทียม Sentinel-2 จริง สมุทรสงคราม ปี ${scene.year}`}
                />
                <span>SENTINEL-2 · SELECTED SCENE</span>
                <i>เปิดภาพเต็ม ↗</i>
              </a>
              <figcaption>
                <div><strong>{scene.year}</strong><span>{sceneRole(scene.year)}</span></div>
                <small>{scene.date} · {scene.tide_level_m_msl.toFixed(3)} m MSL</small>
                <p>{sourceLabel(scene.tide_source_tier)}</p>
                <p>{scene.secondary_bracket_span_minutes == null ? 'hourly interpolation' : `bracket ${Math.round(scene.secondary_bracket_span_minutes)} นาที`}</p>
              </figcaption>
            </figure>
          ))}
        </div>
        <div className="satellite-observation-note">
          <article><strong>สิ่งที่ภาพสอดคล้องกับตัวเลข</strong><p>ภาพรวมแนวขอบน้ำไม่แสดงการถอยเข้าฝั่งแบบพร้อมกันทั้งพื้นที่ ขณะที่แถบพืชริมทะเลหลายช่วงดูต่อเนื่องหรือกว้างขึ้น ซึ่งสอดคล้องกับผล screening แต่ยังมีความคลาดเคลื่อนระดับพิกเซล</p></article>
          <article><strong>สิ่งที่ห้ามอ่านจากภาพโดยตรง</strong><p>น้ำสีต่างกันไม่ได้แปลว่าตะกอนเพิ่มหรือลด และความเขียวเพิ่มไม่ได้แปลว่าการปลูกเป็นสาเหตุ เพราะพื้นที่รอบข้างอาจเปลี่ยนในทิศทางเดียวกัน</p></article>
        </div>
        <p className="asterisk-note">* ยังไม่พบวันปลูกที่ยืนยัน จึงใช้ปี 2024 เป็นช่วงดำเนินการที่กำกวม ไม่ใช่วันเริ่มผลกระทบที่แน่นอน</p>
      </section>

      <section className="report-grid report-grid-secondary">
        <article className="report-panel boundary-panel">
          <div className="report-panel-heading">
            <div><span>03 · WATERLINE</span><h2>ขอบน้ำที่คัดตามระดับน้ำ</h2></div>
            <p>ค่ากึ่งกลาง NSM 2023–2026 = {signed(waterline.median_nsm_2023_2026_m)} ม.</p>
          </div>
          <div className="boundary-counts">
            <div className="inland" style={{ flex: Math.max(waterlineCounts.inland, 1) }}><strong>{waterlineCounts.inland}</strong><span>เข้าฝั่ง &gt;20 ม.</span></div>
            <div className="within" style={{ flex: Math.max(waterlineCounts.within, 1) }}><strong>{waterlineCounts.within}</strong><span>อยู่ใน ±20 ม.</span></div>
            <div className="seaward" style={{ flex: Math.max(waterlineCounts.seaward, 1) }}><strong>{waterlineCounts.seaward}</strong><span>ออกทะเล &gt;20 ม.</span></div>
          </div>
          <div className="boundary-summary">
            <div><span>Median NSM</span><strong>{valueOrDash(waterline.median_nsm_2023_2026_m, ' m')}</strong></div>
            <div><span>Median EPR</span><strong>{valueOrDash(waterline.median_epr_2023_2026_m_per_year, ' m/y')}</strong></div>
            <div><span>Role</span><strong>Supporting</strong></div>
          </div>
          <p className="panel-disclaimer">เป็น image-derived waterline ที่คัดภาพตามระดับน้ำ ไม่ใช่ surveyed หรือ tide-normalized shoreline</p>
        </article>

        <article className="report-panel boundary-panel">
          <div className="report-panel-heading">
            <div><span>04 · MANGROVE EDGE PROXY</span><h2>ขอบพืชด้านทะเล</h2></div>
            <p>NDVI ≥ 0.35 · composite มกราคม–เมษายน</p>
          </div>
          <div className="boundary-counts">
            <div className="inland" style={{ flex: Math.max(mangroveCounts.inland, 1) }}><strong>{mangroveCounts.inland}</strong><span>เข้าฝั่ง &gt;20 ม.</span></div>
            <div className="within" style={{ flex: Math.max(mangroveCounts.within, 1) }}><strong>{mangroveCounts.within}</strong><span>อยู่ใน ±20 ม.</span></div>
            <div className="seaward" style={{ flex: Math.max(mangroveCounts.seaward, 1) }}><strong>{mangroveCounts.seaward}</strong><span>ออกทะเล &gt;20 ม.</span></div>
          </div>
          <div className="boundary-summary">
            <div><span>Median NSM</span><strong>{valueOrDash(mangrove.median_nsm_2023_2026_m, ' m')}</strong></div>
            <div><span>Proxy area</span><strong>{signed(vegetationAreaChange, 1)} ha</strong></div>
            <div><span>Role</span><strong>Primary screening</strong></div>
          </div>
          <p className="panel-disclaimer">เป็นขอบ vegetation spectral proxy ไม่ใช่แผนที่ป่าชายเลนที่ผ่านการตรวจ confusion matrix</p>
        </article>
      </section>

      <section className="report-panel plot-table-panel">
        <div className="report-panel-heading">
          <div><span>05 · PLOT AND CONTROL COMPARISON</span><h2>ผลคัดกรองรายแปลง</h2></div>
          <p>ค่าบวกหมายถึงเคลื่อนออกทะเลมากกว่า หรือถอยเข้าฝั่งน้อยกว่า control</p>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>แปลง</th>
                <th>ขอบเขตการใช้ผล</th>
                <th>Transects</th>
                <th>Waterline<br />NSM</th>
                <th>Waterline<br />เทียบ control</th>
                <th>Mangrove proxy<br />NSM</th>
                <th>Mangrove proxy<br />เทียบ control</th>
                <th>สถานะ</th>
              </tr>
            </thead>
            <tbody>
              {summary.per_plot.map((plot) => {
                const eligibility = plot.coastal_eligibility
                const excluded = eligibility.coastal_erosion_scope === 'EXCLUDED_FROM_COASTAL_SCREENING'
                return (
                  <tr key={plot.plot_id}>
                    <td><strong>{plot.plot_id}</strong></td>
                    <td>{scopeLabel(eligibility.coastal_erosion_scope)}</td>
                    <td>{eligibility.treatment_transect_count}</td>
                    <td>{signed(plot.waterline.median_nsm_2023_2026_m)} m</td>
                    <td>{signed(plot.waterline.screening_difference_m)} m</td>
                    <td>{signed(plot.mangrove_edge_proxy.median_nsm_2023_2026_m)} m</td>
                    <td>{signed(plot.mangrove_edge_proxy.screening_difference_m)} m</td>
                    <td>
                      <span className={`confidence-pill ${excluded ? 'excluded' : ''}`}>
                        {excluded ? `${eligibility.distance_to_2026_waterline_m.toFixed(0)} ม. จาก waterline` : 'LOW'}
                      </span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        <p className="table-note">Candidate controls ยังไม่ได้ตรวจโครงสร้างชายฝั่ง การขุดลอก การถม และประวัติปลูก จึงเป็นเพียง screening comparison ไม่ใช่ causal effect</p>
      </section>

      <section className="report-conclusion">
        <div>
          <span>06 · CURRENT INTERPRETATION</span>
          <h2>คำตอบจากภาพและข้อมูลชุดนี้</h2>
        </div>
        <ol>
          <li><strong>Waterline:</strong> ค่ากึ่งกลางทั้งโครงการเท่ากับ {signed(waterline.median_nsm_2023_2026_m)} เมตร และ {waterlineCounts.within} จาก {waterline.transect_count} แนวอยู่ภายใน ±20 เมตร</li>
          <li><strong>ขอบพืช:</strong> vegetation-edge proxy มีค่ากึ่งกลาง {signed(mangrove.median_nsm_2023_2026_m)} เมตร แต่ยังไม่ผ่านการตรวจด้วยโดรนหรือภาคสนาม</li>
          <li><strong>พื้นที่ควบคุม:</strong> มี {summary.controls.selected_count} candidate controls สำหรับ 8 แปลงชายฝั่ง แต่ยังไม่ยืนยันปัจจัยรบกวน</li>
          <li><strong>87-VSD:</strong> อยู่ห่าง waterline ที่สกัดได้ประมาณ {excluded87?.coastal_eligibility.distance_to_2026_waterline_m.toFixed(0) ?? '—'} เมตร จึงไม่รวมในการเคลมการกัดเซาะชายฝั่ง และควรวิเคราะห์ BANK_EDGE แยก</li>
          <li><strong>ข้อสรุป:</strong> ภาพก่อน–หลังช่วยให้เห็นบริบทและตรวจความสมเหตุสมผลของผลคำนวณ แต่ยังไม่รองรับข้อความว่าโครงการลดการกัดเซาะแล้ว</li>
        </ol>
      </section>

      <section className="report-panel methodology-panel">
        <div className="report-panel-heading">
          <div><span>07 · METHOD, DOWNLOADS & LIMITS</span><h2>วิธีวิเคราะห์และไฟล์ตรวจสอบ</h2></div>
          <div className="download-links">
            <a href="data/project_tide_aware/summary.json" download>Summary JSON</a>
            <a href="data/project_tide_aware/transect_metrics.csv" download>Transect CSV</a>
            <a href="data/project_tide_aware/candidate_controls.csv" download>Controls CSV</a>
            <a href="data/project_tide_aware/plot_coastal_eligibility.csv" download>Eligibility CSV</a>
          </div>
        </div>
        <div className="method-grid">
          <div><strong>Scene selection</strong><p>หนึ่ง acquisition ต่อปี เลือกให้ระดับน้ำข้ามปีใกล้กันที่สุด และ secondary bracket ไม่เกิน 12 ชั่วโมง</p></div>
          <div><strong>Waterline</strong><p>MNDWI จาก Sentinel-2 ที่เลือก · ใช้สนับสนุนเท่านั้น</p></div>
          <div><strong>Mangrove proxy</strong><p>NDVI ≥ 0.35 จาก median composite ฤดูกาลเดียวกัน</p></div>
          <div><strong>Controls</strong><p>นอก buffer แปลง 150 เมตร จับคู่ระยะและ pretrend 2023–2024</p></div>
        </div>
        <p className="panel-disclaimer">{summary.waterline_scene_selection.scientific_limit}</p>
        <ul className="limitation-list">{summary.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
      </section>

      <footer className="report-footer">
        <span>Samut Songkhram Tide-aware Coastal Screening</span>
        <p>Real Sentinel-2 imagery · Predicted-tide screening · Not a surveyed, tide-normalized, causal, or engineering shoreline report.</p>
      </footer>
    </main>
  )
}
