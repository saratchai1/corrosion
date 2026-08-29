import { useCallback, useEffect, useMemo, useState } from 'react'
import MapPane from './MapPane'
import ProjectDashboard from './ProjectDashboard'
import TransectChart from './TransectChart'
import type { DataIndex, ProjectImpactSummary, Summary, TransectSelection, ViewState } from './types'

const initialView: ViewState = { center: [100.005, 13.345], zoom: 10.7, bearing: 0, pitch: 0 }

export default function App() {
  const [page, setPage] = useState<'project' | 'coast'>('coast')
  const [index, setIndex] = useState<DataIndex | null>(null)
  const [summary, setSummary] = useState<Summary | null>(null)
  const [projectSummary, setProjectSummary] = useState<ProjectImpactSummary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [yearIndex, setYearIndex] = useState(0)
  const [compare, setCompare] = useState(false)
  const [compareIndex, setCompareIndex] = useState(0)
  const [view, setView] = useState<ViewState>(initialView)
  const [opacity, setOpacity] = useState(0.82)
  const [selection, setSelection] = useState<TransectSelection | null>(null)
  const [layers, setLayers] = useState({ imagery: true, boundary: true, vegetation: false, transects: true, plots: true })

  useEffect(() => {
    Promise.all([
      fetch('data/index.json').then((response) => response.json()),
      fetch('data/summary.json').then((response) => response.json()),
      fetch('data/project/summary.json').then((response) => response.json()),
    ])
      .then(([indexData, summaryData, projectSummaryData]) => {
        setIndex(indexData as DataIndex)
        setSummary(summaryData as Summary)
        setProjectSummary(projectSummaryData as ProjectImpactSummary)
        setYearIndex((indexData as DataIndex).epochs.length - 1)
        const prePlantingIndex = (indexData as DataIndex).epochs.findIndex((item) => item.targetYear === 2023)
        setCompareIndex(prePlantingIndex >= 0 ? prePlantingIndex : 0)
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : String(reason)))
  }, [])

  const epoch = index?.epochs[yearIndex]
  const compareEpoch = index?.epochs[compareIndex]
  const handleTransect = useCallback((value: TransectSelection) => setSelection(value), [])
  const layerOptions = useMemo(() => [
    ['imagery', 'ภาพดาวเทียม', 'Imagery'],
    ['boundary', 'ขอบเขตน้ำ–แผ่นดิน', 'Water–land'],
    ['vegetation', 'พืชชายฝั่ง (proxy)', 'Vegetation proxy'],
    ['transects', 'แนววัดการเปลี่ยนแปลง', 'Transects'],
    ['plots', 'แปลงปลูกปี 2024', '9 verified project plots'],
  ] as const, [])

  if (error) return <main className="loading">โหลดข้อมูลไม่สำเร็จ / Failed to load: {error}</main>
  if (!index || !summary || !projectSummary || !epoch || !compareEpoch) return <main className="loading">กำลังเปิดชุดข้อมูลชายฝั่ง…</main>

  if (page === 'project') return <ProjectDashboard summary={projectSummary} onOpenCoast={() => setPage('coast')} />

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="coast-view-tabs view-tabs" role="tablist" aria-label="เลือกมุมมอง">
          <button role="tab" aria-selected="false" onClick={() => setPage('project')}>รายงานผล 9 แปลง</button>
          <button className="active" role="tab" aria-selected="true">แผนที่ดาวเทียม 10 ปี</button>
        </div>
        <header>
          <span className="project-tag">ANNUAL SATELLITE IMAGERY · 2017–2026</span>
          <h1>แผนที่ภาพดาวเทียม<br /><em>10-year timeline</em></h1>
          <p>ภาพ Sentinel-2 ครบรายปี 10 ปีล่าสุด พร้อมภาพประวัติศาสตร์ Landsat ย้อนถึงปี 1987 และชั้นข้อมูลการเปลี่ยนแปลงชายฝั่ง</p>
        </header>

        <section className="summary-grid">
          <article title="Sentinel-2 ครบรายปี 2017–2026 และมีภาพประวัติศาสตร์ Landsat อีก 4 ช่วง"><span>ภาพรายปีล่าสุด</span><strong>2017–2026</strong><small>10 annual + 4 historical</small></article>
          <article title="ผลรวมช่วง transect ที่ขอบเขตน้ำ–แผ่นดินเคลื่อนเข้าฝั่งเกินความละเอียด 30 เมตร; tide unverified"><span>แนวถอยร่นที่ปรากฏ</span><strong>{summary.apparent_erosion_length_km.toFixed(1)} km</strong><small>LOW confidence</small></article>
          <article title="ผลรวมช่วง transect ที่ขอบเขตน้ำ–แผ่นดินเคลื่อนออกทะเลเกินความละเอียด 30 เมตร; tide unverified"><span>แนวงอกเพิ่มที่ปรากฏ</span><strong>{summary.apparent_accretion_length_km.toFixed(1)} km</strong><small>transect estimate</small></article>
          <article title="ช่วงที่การเปลี่ยนแปลงอยู่ภายใน ±30 เมตร จึงไม่ควรตีความทิศทาง"><span>คงที่ในช่วงความละเอียด</span><strong>{summary.stable_length_km.toFixed(1)} km</strong><small>within ±30 m</small></article>
          <article title="ผลต่างพื้นที่ vegetation spectral proxy ระหว่าง epoch แรกและล่าสุด; ไม่ใช่บัญชีป่าชายเลนที่ผ่านการตรวจสอบ"><span>พืชชายฝั่ง proxy</span><strong>{summary.vegetation_proxy_change_ha >= 0 ? '+' : ''}{summary.vegetation_proxy_change_ha.toFixed(0)} ha</strong><small>{summary.vegetation_proxy_change_percent.toFixed(1)}%</small></article>
          <article title="ค่ากึ่งกลางการเคลื่อนที่สุทธิของ transect ที่มีข้อมูล; ค่าบวกหมายถึงออกทะเล"><span>ค่ากึ่งกลางสุทธิ</span><strong>{summary.median_net_change_m?.toFixed(0) ?? '—'} m</strong><small>positive = seaward</small></article>
        </section>

        <section className="control-section timeline-section">
          <div className="section-heading"><span>01</span><h2>ภาพย้อนหลัง / Imagery timeline</h2></div>
          <div className="timeline-scope"><span>10 ปีล่าสุดครบรายปี</span><strong>2017—2026</strong><small>+ historical snapshots: 1985 / 1990 / 2000 / 2010</small></div>
          <div className="year-readout"><strong>{epoch.targetYear}</strong><span>{epoch.targetYear === 2024 ? 'ปีดำเนินการปลูก*' : `ภาพจริง ${epoch.actualYear}`}<br />{epoch.sensor} · {epoch.resolutionM} m</span></div>
          <input aria-label="Select epoch" type="range" min="0" max={index.epochs.length - 1} value={yearIndex} onChange={(event) => setYearIndex(Number(event.target.value))} />
          <div className="tick-row">{index.epochs.map((item, itemIndex) => <button
            key={item.targetYear}
            title={`${item.targetYear}${item.targetYear === 2024 ? ' · ปีดำเนินการปลูก' : ''}`}
            className={`${itemIndex === yearIndex ? 'active' : ''} ${item.targetYear === 2017 ? 'decade-start' : ''} ${item.targetYear === 2024 ? 'intervention-year' : ''}`}
            onClick={() => setYearIndex(itemIndex)}
          >{String(item.targetYear).slice(2)}</button>)}</div>
          <div className="timeline-presets">
            <button onClick={() => setYearIndex(index.epochs.findIndex((item) => item.targetYear === 2017))}>2017 · เริ่ม 10 ปี</button>
            <button className="intervention" onClick={() => setYearIndex(index.epochs.findIndex((item) => item.targetYear === 2024))}>2024 · ปีปลูก*</button>
            <button onClick={() => setYearIndex(index.epochs.length - 1)}>2026 · ล่าสุด</button>
          </div>
          <label className="switch-row"><span><strong>เปรียบเทียบสองช่วงเวลา</strong><small>Side-by-side, synchronized maps</small></span><input type="checkbox" checked={compare} onChange={(event) => setCompare(event.target.checked)} /><i /></label>
          {compare && <label className="compare-select">แผนที่ซ้าย / left<select value={compareIndex} onChange={(event) => setCompareIndex(Number(event.target.value))}>{index.epochs.map((item, itemIndex) => <option value={itemIndex} key={item.targetYear}>{item.targetYear} (ภาพ {item.actualYear})</option>)}</select></label>}
        </section>

        <section className="control-section">
          <div className="section-heading"><span>02</span><h2>ชั้นข้อมูล / Layers</h2></div>
          <div className="layer-list">{layerOptions.map(([key, thai, english]) => <label key={key}><input type="checkbox" checked={layers[key]} onChange={(event) => setLayers((current) => ({ ...current, [key]: event.target.checked }))} /><i className={`swatch ${key}`} /><span><strong>{thai}</strong><small>{english}</small></span></label>)}</div>
          <label className="opacity">ความทึบภาพ / Imagery opacity <strong>{Math.round(opacity * 100)}%</strong><input type="range" min="0" max="1" step="0.05" value={opacity} onChange={(event) => setOpacity(Number(event.target.value))} /></label>
        </section>

        {projectSummary && <section className="project-result">
          <span className="eyebrow">2024 PLANTING ASSESSMENT · LOW CONFIDENCE</span>
          <h2>ผลเฉพาะ 9 แปลง</h2>
          <strong>ยังไม่พิสูจน์ว่าลดการกัดเซาะ</strong>
          <p>{projectSummary.conclusion_th}</p>
          <dl>
            <div><dt>แปลง</dt><dd>{projectSummary.plot_count}</dd></div>
            <div><dt>พื้นที่ทางการ</dt><dd>{projectSummary.official_participating_area_rai.toFixed(1)} ไร่</dd></div>
            <div><dt>NDVI DiD ปี 2026</dt><dd>{projectSummary.difference_in_differences.find((item) => item.post_year === 2026)?.ndvi_difference_in_differences.toFixed(3) ?? '—'}</dd></div>
            <div><dt>ขอบเขตใน ±20 ม.</dt><dd>{projectSummary.post_boundary_evidence.within_20m_count}/{projectSummary.post_boundary_evidence.transect_count}</dd></div>
          </dl>
        </section>}

        {selection ? <TransectChart selection={selection} /> : <section className="empty-chart"><span>03</span><p>คลิกแนว transect บนแผนที่เพื่อดูกราฟตำแหน่งขอบเขตตามเวลา</p><small>Click a transect for its time series.</small></section>}

        <footer>
          <strong>ข้อจำกัดสำคัญ / Critical limitation</strong>
          <p>{index.disclaimer_th}</p>
          <p>{index.disclaimer_en}</p>
          <span>ระดับน้ำ: ไม่ผ่านการตรวจสอบ · Tide status: UNVERIFIED</span>
        </footer>
      </aside>

      <section className={`map-stage ${compare ? 'is-compare' : ''}`}>
        {compare && <MapPane epoch={compareEpoch} label="A · BEFORE" layers={layers} opacity={opacity} sharedView={view} onView={setView} onTransect={handleTransect} />}
        <MapPane epoch={epoch} label={compare ? 'B · AFTER' : 'SELECTED EPOCH'} layers={layers} opacity={opacity} sharedView={view} onView={setView} onTransect={handleTransect} />
        <div className="legend"><span><i className="erosion" /> apparent erosion</span><span><i className="accretion" /> apparent accretion</span><span><i className="stable" /> within resolution</span></div>
      </section>
    </main>
  )
}
