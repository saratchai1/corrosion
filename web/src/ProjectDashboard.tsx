import ProjectMap from './ProjectMap'
import type { ProjectImpactSummary } from './types'

type Props = {
  summary: ProjectImpactSummary
  onOpenCoast: () => void
}

type TrendSeries = {
  label: string
  color: string
  values: number[]
}

function signed(value: number, digits = 3): string {
  return `${value >= 0 ? '+' : ''}${value.toFixed(digits)}`
}

function percent(value: number, digits = 1): string {
  return `${(value * 100).toFixed(digits)}%`
}

function TrendChart({ years, series, format, label }: {
  years: number[]
  series: TrendSeries[]
  format: (value: number) => string
  label: string
}) {
  const width = 680
  const height = 270
  const margin = { left: 58, right: 24, top: 32, bottom: 42 }
  const values = series.flatMap((item) => item.values)
  const dataMin = Math.min(...values)
  const dataMax = Math.max(...values)
  const padding = Math.max((dataMax - dataMin) * 0.22, 0.01)
  const minimum = dataMin - padding
  const maximum = dataMax + padding
  const x = (index: number) => margin.left + index * ((width - margin.left - margin.right) / Math.max(years.length - 1, 1))
  const y = (value: number) => margin.top + (maximum - value) / (maximum - minimum) * (height - margin.top - margin.bottom)
  const ticks = Array.from({ length: 5 }, (_, index) => minimum + index * (maximum - minimum) / 4)

  return (
    <div className="report-chart">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label}>
        <rect className="intervention-band" x={x(1) - 46} y={margin.top} width="92" height={height - margin.top - margin.bottom} />
        <text className="intervention-label" x={x(1)} y="19" textAnchor="middle">ปีดำเนินการ*</text>
        {ticks.map((tick) => <g key={tick}>
          <line className="report-grid-line" x1={margin.left} x2={width - margin.right} y1={y(tick)} y2={y(tick)} />
          <text className="report-axis-label" x={margin.left - 10} y={y(tick) + 4} textAnchor="end">{format(tick)}</text>
        </g>)}
        {years.map((year, index) => <text className="report-axis-label" key={year} x={x(index)} y={height - 14} textAnchor="middle">{year}</text>)}
        {series.map((item) => {
          const path = item.values.map((value, index) => `${index === 0 ? 'M' : 'L'} ${x(index)} ${y(value)}`).join(' ')
          return <g key={item.label}>
            <path d={path} fill="none" stroke={item.color} strokeWidth="3" />
            {item.values.map((value, index) => <g key={`${item.label}-${years[index]}`}>
              <circle cx={x(index)} cy={y(value)} r="5" fill={item.color} stroke="#0c292b" strokeWidth="2" />
              <text className="report-value-label" x={x(index)} y={y(value) - 11} textAnchor="middle">{format(value)}</text>
            </g>)}
          </g>
        })}
      </svg>
      <div className="report-chart-legend">{series.map((item) => <span key={item.label}><i style={{ background: item.color }} />{item.label}</span>)}</div>
    </div>
  )
}

function plotBoundaryStatus(boundary: ProjectImpactSummary['post_boundary_evidence']['per_plot'][number] | undefined): string {
  if (!boundary) return 'ไม่มี transect'
  if (boundary.apparent_inland_count > 0 && boundary.apparent_seaward_count > 0) return 'ผลผสม'
  if (boundary.apparent_inland_count > 0) return 'มีสัญญาณเข้าฝั่ง'
  if (boundary.apparent_seaward_count > 0) return 'มีสัญญาณออกทะเล'
  return 'อยู่ใน ±20 ม.'
}

export default function ProjectDashboard({ summary, onOpenCoast }: Props) {
  const baseline = summary.project_yearly_metrics.find((item) => item.year === 2023)!
  const latest = summary.project_yearly_metrics.find((item) => item.year === 2026)!
  const did2026 = summary.difference_in_differences.find((item) => item.post_year === 2026)!
  const boundary = summary.post_boundary_evidence
  const stablePercent = boundary.within_20m_count / boundary.transect_count
  const ndviChange = latest.mean_ndvi - baseline.mean_ndvi
  const vegetationChange = latest.vegetation_fraction_ndvi_gte_0_35 - baseline.vegetation_fraction_ndvi_gte_0_35
  const comparison = summary.matched_control_comparison
  const boundaryByPlot = new Map(boundary.per_plot.map((item) => [item.plot_id, item]))

  return (
    <main className="report-shell">
      <nav className="report-nav">
        <div><span>สมุทรสงคราม</span><strong>Mangrove Impact Monitor</strong></div>
        <div className="view-tabs" role="tablist" aria-label="เลือกมุมมอง">
          <button className="active" role="tab" aria-selected="true">รายงาน 9 แปลง</button>
          <button role="tab" aria-selected="false" onClick={onOpenCoast}>แผนที่ชายฝั่ง 1985–2026</button>
        </div>
      </nav>

      <header className="report-hero">
        <div className="report-hero-copy">
          <span className="report-kicker">SATELLITE IMPACT ASSESSMENT · UPDATED 2026</span>
          <h1>ปลูกป่าชายเลนปี 2024<br /><em>ลดการกัดเซาะได้ไหม?</em></h1>
          <p>รายงานเชิงสำรวจจาก Sentinel-2 ครอบคลุม 9 แปลง จังหวัดสมุทรสงคราม เปรียบเทียบก่อนปลูก ปีดำเนินการ และสองปีหลังดำเนินการ</p>
        </div>
        <article className="verdict-card">
          <div className="verdict-status"><i />ผลประเมิน · LOW CONFIDENCE</div>
          <strong>ยังไม่พิสูจน์<br />ว่าลดการกัดเซาะ</strong>
          <p>พื้นที่แปลงเขียวขึ้นและแนวน้ำส่วนใหญ่ทรงตัว แต่พื้นที่เทียบเขียวขึ้นใกล้เคียงกัน จึงยังระบุไม่ได้ว่าการปลูกเป็นสาเหตุ</p>
          <span>EROSION EFFECT: {summary.erosion_effect_conclusion}</span>
        </article>
      </header>

      <section className="report-kpis" aria-label="ตัวชี้วัดสำคัญ">
        <article><span>ขอบเขตโครงการ</span><strong>{summary.plot_count}</strong><small>แปลงที่ตรวจสอบแล้ว</small></article>
        <article><span>พื้นที่ทางการ</span><strong>{summary.official_participating_area_rai.toFixed(1)}</strong><small>ไร่</small></article>
        <article className="positive"><span>NDVI ในแปลง</span><strong>{signed(ndviChange)}</strong><small>2023 → 2026</small></article>
        <article><span>NDVI เทียบควบคุม</span><strong>{signed(did2026.ndvi_difference_in_differences)}</strong><small>Difference-in-Differences</small></article>
        <article><span>แนวน้ำใน ±20 ม.</span><strong>{percent(stablePercent, 0)}</strong><small>{boundary.within_20m_count} จาก {boundary.transect_count} แนว</small></article>
        <article className="caution"><span>ค่ากึ่งกลางการเคลื่อนที่</span><strong>{boundary.median_movement_m?.toFixed(2)}</strong><small>เมตร · 2025–2026</small></article>
      </section>

      <section className="report-grid report-grid-primary">
        <article className="report-panel trend-panel">
          <div className="report-panel-heading">
            <div><span>01 · VEGETATION SIGNAL</span><h2>ความเขียวในแปลงเทียบพื้นที่ใกล้เคียง</h2></div>
            <p>ค่า NDVI เพิ่มทั้งสองกลุ่ม จึงยังแยกผลจากการปลูกไม่ได้ชัดเจน</p>
          </div>
          <TrendChart
            years={comparison.map((item) => item.year)}
            series={[
              { label: '9 แปลงโครงการ', color: '#67d983', values: comparison.map((item) => item.impact_mean_ndvi) },
              { label: 'พื้นที่เทียบใกล้เคียง', color: '#ff9f6e', values: comparison.map((item) => item.control_mean_ndvi) },
            ]}
            format={(value) => value.toFixed(3)}
            label="กราฟแนวโน้ม NDVI ของแปลงโครงการและพื้นที่เทียบ ปี 2023 ถึง 2026"
          />
          <div className="chart-insight"><strong>+{ndviChange.toFixed(3)}</strong><span>NDVI เพิ่มในแปลง</span><i /> <strong>{signed(did2026.ndvi_difference_in_differences)}</strong><span>เหลือเมื่อหักแนวโน้มพื้นที่เทียบ</span></div>
        </article>

        <article className="report-panel map-panel">
          <div className="report-panel-heading">
            <div><span>02 · PROJECT FOOTPRINT</span><h2>แผนที่ 9 แปลง</h2></div>
            <p>สีม่วง: 91–98-STC · สีส้ม: 87-VSD</p>
          </div>
          <ProjectMap />
          <div className="map-note">คลิก Polygon เพื่อดูรหัสและพื้นที่ทางการ · Geometry ใช้เพื่อวิเคราะห์ ไม่แทนเอกสารสิทธิ์</div>
        </article>
      </section>

      <section className="report-panel imagery-panel">
        <div className="report-panel-heading">
          <div><span>03 · SAME-SEASON IMAGERY</span><h2>ภาพดาวเทียมฤดูเดียวกัน 2023–2026</h2></div>
          <p>Median composite เดือนมกราคม–เมษายน ปีละ 3 acquisition</p>
        </div>
        <div className="imagery-timeline">
          {summary.project_yearly_metrics.map((item) => <figure key={item.year} className={item.year === 2024 ? 'intervention' : ''}>
            <a className="satellite-image" href={`data/project/${item.year}.webp`} target="_blank" rel="noreferrer" aria-label={`เปิดภาพดาวเทียม Sentinel-2 ปี ${item.year} ขนาดเต็ม`}>
              <img src={`data/project/${item.year}.webp`} alt={`ภาพ Sentinel-2 true-color composite ปี ${item.year} สำหรับแปลงสมุทรสงคราม`} />
              <span>SENTINEL-2 · TRUE COLOR</span>
              <i>เปิดภาพเต็ม ↗</i>
            </a>
            <figcaption>
              <div><strong>{item.year}</strong><span>{item.year === 2023 ? 'ก่อนดำเนินการ' : item.year === 2024 ? 'ปีดำเนินการ*' : 'หลังดำเนินการ'}</span></div>
              <small>NDVI {item.mean_ndvi.toFixed(3)}</small>
              <p>{item.scene_dates.split(';').join(' · ')}</p>
              <p>{item.sensor}</p>
            </figcaption>
          </figure>)}
        </div>
        <p className="asterisk-note">* ไม่พบวันปลูกที่ยืนยัน จึงถือภาพปี 2024 เป็นช่วงดำเนินการที่กำกวม</p>
      </section>

      <section className="report-grid report-grid-secondary">
        <article className="report-panel boundary-panel">
          <div className="report-panel-heading">
            <div><span>04 · WATER–LAND EVIDENCE</span><h2>ขอบเขตน้ำ–แผ่นดิน 2025–2026</h2></div>
            <p>43 transects ที่ตัดผ่าน 91–98-STC</p>
          </div>
          <div className="boundary-counts">
            <div className="inland" style={{ flex: boundary.apparent_inland_count }}><strong>{boundary.apparent_inland_count}</strong><span>เข้าฝั่ง &gt;20 ม.</span></div>
            <div className="within" style={{ flex: boundary.within_20m_count }}><strong>{boundary.within_20m_count}</strong><span>อยู่ใน ±20 ม.</span></div>
            <div className="seaward" style={{ flex: boundary.apparent_seaward_count }}><strong>{boundary.apparent_seaward_count}</strong><span>ออกทะเล &gt;20 ม.</span></div>
          </div>
          <div className="boundary-summary"><div><span>Median</span><strong>{boundary.median_movement_m?.toFixed(2)} m</strong></div><div><span>Mean</span><strong>{boundary.mean_movement_m?.toFixed(2)} m</strong></div><div><span>Confidence</span><strong>{boundary.confidence}</strong></div></div>
          <p className="panel-disclaimer">เป็น image-derived water–land boundary ไม่ใช่แนวชายฝั่งสำรวจ และยังไม่ได้ปรับระดับน้ำขึ้นลง</p>
        </article>

        <article className="report-panel cover-panel">
          <div className="report-panel-heading">
            <div><span>05 · COVER FRACTION</span><h2>สัดส่วนพืชพรรณในแปลง</h2></div>
            <p>พิกเซล NDVI ≥ 0.35</p>
          </div>
          <TrendChart
            years={summary.project_yearly_metrics.map((item) => item.year)}
            series={[{ label: 'Vegetation proxy', color: '#bd72ff', values: summary.project_yearly_metrics.map((item) => item.vegetation_fraction_ndvi_gte_0_35) }]}
            format={(value) => percent(value, 0)}
            label="กราฟสัดส่วน vegetation proxy ภายในแปลง ปี 2023 ถึง 2026"
          />
          <div className="chart-insight"><strong>+{(vegetationChange * 100).toFixed(1)}</strong><span>percentage points ระหว่าง 2023–2026</span></div>
        </article>
      </section>

      <section className="report-panel plot-table-panel">
        <div className="report-panel-heading">
          <div><span>06 · PLOT-BY-PLOT</span><h2>ผลรายแปลง</h2></div>
          <p>เรียงตามรหัสแปลง · ค่าบวก NDVI หมายถึงเขียวขึ้น</p>
        </div>
        <div className="table-scroll">
          <table>
            <thead><tr><th>แปลง</th><th>Valid pixels</th><th>Δ NDVI<br />2023–2026</th><th>Δ Vegetation<br />fraction</th><th>Δ Water<br />fraction</th><th>Boundary median<br />2025–2026</th><th>สถานะขอบเขต</th><th>ความเชื่อมั่น</th></tr></thead>
            <tbody>{summary.plot_change_summary.map((plot) => {
              const plotBoundary = boundaryByPlot.get(plot.plot_id)
              return <tr key={plot.plot_id}>
                <td><strong>{plot.plot_id}</strong></td>
                <td>{plot.valid_pixels_2023.toLocaleString()}</td>
                <td className="positive-value">{signed(plot.ndvi_change_2023_2026)}</td>
                <td>{signed(plot.vegetation_fraction_change_2023_2026)}</td>
                <td>{signed(plot.water_fraction_change_2023_2026)}</td>
                <td>{plotBoundary?.median_movement_m == null ? '—' : `${signed(plotBoundary.median_movement_m, 2)} m`}</td>
                <td><span className={`table-status ${plotBoundaryStatus(plotBoundary).replaceAll(' ', '-')}`}>{plotBoundaryStatus(plotBoundary)}</span></td>
                <td><span className="confidence-pill">{plot.confidence}</span></td>
              </tr>
            })}</tbody>
          </table>
        </div>
        <p className="table-note">แปลงขนาดเล็ก เช่น 98-STC มีจำนวนพิกเซลน้อย จึงไวต่อ mixed pixel มากกว่าแปลงใหญ่ · 87-VSD อยู่นอก transect AOI เดิม</p>
      </section>

      <section className="report-conclusion">
        <div>
          <span>07 · INTERPRETATION</span>
          <h2>คำตอบที่ข้อมูลรองรับในขณะนี้</h2>
        </div>
        <ol>
          <li><strong>พืชพรรณ:</strong> สัญญาณความเขียวภายในแปลงเพิ่มขึ้นทุกแปลง</li>
          <li><strong>ผลเฉพาะโครงการ:</strong> เมื่อหักแนวโน้มพื้นที่เทียบ ความต่าง NDVI เหลือเพียง {signed(did2026.ndvi_difference_in_differences)}</li>
          <li><strong>ขอบเขตน้ำ:</strong> {boundary.within_20m_count} จาก {boundary.transect_count} แนวอยู่ในช่วง ±20 เมตร แต่ยังมีทั้งจุดถอยและจุดงอก</li>
          <li><strong>ข้อสรุป:</strong> มีสัญญาณการฟื้นตัวของพืชและความทรงตัวบางส่วน แต่ยังไม่ใช่หลักฐานเชิงเหตุว่าการปลูกลดการกัดเซาะ</li>
        </ol>
      </section>

      <section className="report-panel methodology-panel">
        <div className="report-panel-heading">
          <div><span>08 · METHOD & LIMITATIONS</span><h2>วิธีวิเคราะห์และข้อจำกัด</h2></div>
          <div className="download-links"><a href="data/project/summary.json" download>Summary JSON</a><a href="data/project/plot_change_summary.csv" download>Plot CSV</a><a href="data/project/plots.geojson" download>Plot GeoJSON</a></div>
        </div>
        <div className="method-grid">
          <div><strong>ข้อมูล</strong><p>Sentinel-2 L2A · 20 เมตร · 3 ภาพต่อปี · มกราคม–เมษายน</p></div>
          <div><strong>แบบประเมิน</strong><p>2023 ก่อนดำเนินการ · 2024 ช่วงกำกวม · 2025–2026 หลังดำเนินการ</p></div>
          <div><strong>พื้นที่เทียบ</strong><p>บริบทระยะ 200–1,200 เมตร กรองด้วย baseline NDVI และ MNDWI</p></div>
          <div><strong>ระดับน้ำ</strong><p>tide_status=unverified · ห้ามเรียกเส้นนี้ว่าแนวชายฝั่งจริง</p></div>
        </div>
        <ul className="limitation-list">{summary.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
      </section>

      <footer className="report-footer"><span>Samut Songkhram Mangrove Impact Monitor</span><p>Exploratory satellite evidence · Not a legal, cadastral, surveyed, or tide-normalized shoreline report.</p></footer>
    </main>
  )
}
