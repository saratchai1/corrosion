import type { TideAwareIndicatorResult, TideAwareSummary } from './types'

type Props = {
  summary: TideAwareSummary
  onOpenProject: () => void
  onOpenCoast: () => void
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

function indicatorCounts(result: TideAwareIndicatorResult) {
  return {
    inland: result.class_counts.APPARENT_LANDWARD ?? 0,
    within: result.class_counts.WITHIN_20M ?? 0,
    seaward: result.class_counts.APPARENT_SEAWARD ?? 0,
  }
}

export default function TideAwareDashboard({ summary, onOpenProject, onOpenCoast }: Props) {
  const waterline = summary.indicators.waterline
  const mangrove = summary.indicators.mangrove_edge_proxy
  const waterlineCounts = indicatorCounts(waterline)
  const mangroveCounts = indicatorCounts(mangrove)
  const vegetationAreaChange =
    mangrove.area_ha_by_year['2026'] - mangrove.area_ha_by_year['2023']

  return (
    <main className="report-shell">
      <nav className="report-nav">
        <div><span>สมุทรสงคราม</span><strong>Coastal Erosion Evidence</strong></div>
        <div className="view-tabs" role="tablist" aria-label="เลือกมุมมอง">
          <button role="tab" aria-selected="false" onClick={onOpenProject}>รายงาน 9 แปลง</button>
          <button className="active" role="tab" aria-selected="true">คุมระดับน้ำ</button>
          <button role="tab" aria-selected="false" onClick={onOpenCoast}>แผนที่ 10 ปี</button>
        </div>
      </nav>

      <header className="report-hero">
        <div className="report-hero-copy">
          <span className="report-kicker">TIDE-AWARE SCREENING · SENTINEL-2 · 2023–2026</span>
          <h1>คัดภาพระดับน้ำใกล้กัน<br /><em>แล้วชายฝั่งเปลี่ยนอย่างไร?</em></h1>
          <p>
            เลือกภาพ Sentinel-2 ปีละหนึ่งวันด้วยระดับน้ำทำนายที่ใกล้เคียงกัน แยกขอบน้ำออกจากขอบพืช
            และเปรียบเทียบหน้าแปลงกับแนวควบคุมเบื้องต้น
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

      <section className="report-panel imagery-panel">
        <div className="report-panel-heading">
          <div><span>01 · COMPARABLE-TIDE SCENES</span><h2>ภาพที่ระบบเลือกหลังคุมระดับน้ำ</h2></div>
          <p>ค่าเป้าหมาย {summary.waterline_scene_selection.target_tide_m_msl.toFixed(3)} m MSL · spread {summary.waterline_scene_selection.tide_spread_m.toFixed(3)} m</p>
        </div>
        <div className="imagery-timeline">
          {summary.waterline_scene_selection.selected_scenes.map((scene) => (
            <figure key={scene.year}>
              <a
                className="satellite-image"
                href={`data/project_tide_aware/imagery/${scene.year}_selected.webp`}
                target="_blank"
                rel="noreferrer"
                aria-label={`เปิดภาพ Sentinel-2 ที่คัดตามระดับน้ำ ปี ${scene.year}`}
              >
                <img
                  src={`data/project_tide_aware/imagery/${scene.year}_selected.webp`}
                  alt={`ภาพ Sentinel-2 สมุทรสงครามที่คัดตามระดับน้ำ ปี ${scene.year}`}
                />
                <span>SENTINEL-2 · SELECTED SCENE</span>
                <i>เปิดภาพเต็ม ↗</i>
              </a>
              <figcaption>
                <div><strong>{scene.year}</strong><span>{scene.date}</span></div>
                <small>{scene.tide_level_m_msl.toFixed(3)} m MSL</small>
                <p>{sourceLabel(scene.tide_source_tier)}</p>
                <p>{scene.secondary_bracket_span_minutes == null ? 'hourly interpolation' : `bracket ${Math.round(scene.secondary_bracket_span_minutes)} นาที`}</p>
              </figcaption>
            </figure>
          ))}
        </div>
        <p className="asterisk-note">
          ระดับน้ำเป็นค่าทำนายของสถานีปากน้ำแม่กลอง ไม่ใช่ค่าที่วัดตรงหน้าแปลง และยังไม่ได้แปลงความต่างระดับน้ำเป็นระยะทางแนวราบ
        </p>
      </section>

      <section className="report-grid report-grid-secondary">
        <article className="report-panel boundary-panel">
          <div className="report-panel-heading">
            <div><span>02 · WATERLINE</span><h2>ขอบน้ำที่คัดตามระดับน้ำ</h2></div>
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
            <div><span>03 · MANGROVE EDGE PROXY</span><h2>ขอบพืชด้านทะเล</h2></div>
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
          <div><span>04 · PLOT AND CONTROL COMPARISON</span><h2>ผลคัดกรองรายแปลง</h2></div>
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
        <p className="table-note">
          Candidate controls ยังไม่ได้ตรวจโครงสร้างชายฝั่ง การขุดลอก การถม และประวัติปลูก จึงเป็นเพียง screening comparison ไม่ใช่ causal effect
        </p>
      </section>

      <section className="report-conclusion">
        <div>
          <span>05 · CURRENT INTERPRETATION</span>
          <h2>คำตอบจากข้อมูลชุดนี้</h2>
        </div>
        <ol>
          <li><strong>Waterline:</strong> ค่ากึ่งกลางทั้งโครงการเท่ากับ {signed(waterline.median_nsm_2023_2026_m)} เมตร และ {waterlineCounts.within} จาก {waterline.transect_count} แนวอยู่ภายใน ±20 เมตร</li>
          <li><strong>ขอบพืช:</strong> vegetation-edge proxy มีค่ากึ่งกลาง {signed(mangrove.median_nsm_2023_2026_m)} เมตร แต่ยังไม่ผ่านการตรวจด้วยโดรนหรือภาคสนาม</li>
          <li><strong>พื้นที่ควบคุม:</strong> มี {summary.controls.selected_count} candidate controls สำหรับ 8 แปลงชายฝั่ง แต่ยังไม่ยืนยันปัจจัยรบกวน</li>
          <li><strong>87-VSD:</strong> อยู่ห่าง waterline ที่สกัดได้ประมาณ {summary.per_plot.find((item) => item.plot_id === '87-VSD')?.coastal_eligibility.distance_to_2026_waterline_m.toFixed(0)} เมตร จึงไม่รวมในการเคลมการกัดเซาะชายฝั่ง และควรวิเคราะห์ BANK_EDGE แยก</li>
          <li><strong>ข้อสรุป:</strong> ข้อมูลรองรับการติดตามแนวโน้มแบบ tide-aware แต่ยังไม่รองรับข้อความว่าโครงการลดการกัดเซาะแล้ว</li>
        </ol>
      </section>

      <section className="report-panel methodology-panel">
        <div className="report-panel-heading">
          <div><span>06 · METHOD, DOWNLOADS & LIMITS</span><h2>วิธีวิเคราะห์และไฟล์ตรวจสอบ</h2></div>
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
        <ul className="limitation-list">{summary.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
      </section>

      <footer className="report-footer">
        <span>Samut Songkhram Tide-aware Coastal Screening</span>
        <p>Predicted-tide satellite screening · Not a surveyed, tide-normalized, causal, or engineering shoreline report.</p>
      </footer>
    </main>
  )
}
