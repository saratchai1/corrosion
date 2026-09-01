import { useCallback, useEffect, useMemo, useState } from 'react'
import MapPane from './MapPane'
import SwipeCompare from './SwipeCompare'
import type { DataIndex, EvidenceManifest, ExecutiveSummary, LayerVisibility, TransectSelection, ViewState } from './types'

const initialView: ViewState = { center: [99.231, 9.343], zoom: 12.2, bearing: 0, pitch: 0 }

const statusLabel = (value?: string) => {
  if (!value) return 'รอตรวจสอบ'
  if (value.includes('SMALL_POSITIVE')) return 'สัญญาณบวกเล็กน้อย'
  if (value.includes('NO_DETECTABLE')) return 'ยังไม่พบการขยายตัวระดับ 10 ม.'
  if (value.includes('FAILED')) return 'ไม่ผ่าน robustness'
  if (value.includes('PASSED')) return 'ผ่าน QA'
  if (value.includes('NOT_SUPPORTED')) return 'ยังไม่รองรับข้อสรุปเชิงเหตุผล'
  return value.replaceAll('_', ' ')
}

function Metric({ label, value, note, tone = '' }: { label: string; value: string; note: string; tone?: string }) {
  return <article className={`metric ${tone}`}><span>{label}</span><strong>{value}</strong><small>{note}</small></article>
}

type Props = { index: DataIndex; exec: ExecutiveSummary; manifest: EvidenceManifest }

export default function HistoryPage({ index, exec, manifest }: Props) {
  const [yearIndex, setYearIndex] = useState(index.epochs.length - 1)
  const [beforeIndex, setBeforeIndex] = useState(Math.max(0, index.epochs.findIndex((item) => item.targetYear === 2023)))
  const [compare, setCompare] = useState(false)
  const [view, setView] = useState<ViewState>(initialView)
  const [opacity, setOpacity] = useState(0.92)
  const [selection, setSelection] = useState<TransectSelection | null>(null)
  const [layers, setLayers] = useState<LayerVisibility>({ imagery: true, vegetation: false, waterline: false, vegetationEdge: true, projectBoundary: true, controls: true })

  useEffect(() => {
    const latest = index.epochs.length - 1
    setYearIndex(latest)
    const pre = index.epochs.findIndex((item) => item.targetYear === 2023)
    setBeforeIndex(pre >= 0 ? pre : Math.max(0, latest - 1))
  }, [index])

  const onTransect = useCallback((value: TransectSelection) => setSelection(value), [])
  const layerOptions = useMemo(() => [
    ['imagery', 'ภาพดาวเทียม', 'Satellite imagery'],
    ['vegetationEdge', 'แนวขอบพืชชายฝั่ง', 'PRIMARY · 10 m vegetation-edge transects'],
    ['controls', 'พื้นที่อ้างอิง / Control', 'User-confirmed no known intervention'],
    ['projectBoundary', 'ขอบเขต 37-STC', 'PDD 157.55 rai'],
    ['vegetation', 'พืชชายฝั่ง proxy', 'Annual spectral vegetation mask'],
    ['waterline', 'ขอบน้ำ–แผ่นดิน', 'SUPPORT ONLY · failed robustness'],
  ] as const, [])

  const epoch = index.epochs[yearIndex]
  const before = index.epochs[beforeIndex]
  if (!epoch || !before) return null

  const optical = exec.key_numbers.optical_establishment
  const veg = exec.key_numbers.coastal_vegetation_edge
  const water = exec.key_numbers.waterline_sensitivity
  const post = epoch.targetYear >= 2024
  const pre = epoch.targetYear <= 2023 && epoch.targetYear >= 2017
  const timelineDenominator = Math.max(1, index.epochs.length - 1)

  return <main className="app-shell history-shell">
    <aside className="sidebar">
      <header className="hero">
        <div className="project-tag">SURAT THANI · 37-STC · MULTI-YEAR HISTORY</div>
        <h1>ชายฝั่งไชยา<br/><em>ก่อน–หลังการปลูก</em></h1>
        <p>หน้าหลักเก็บประวัติหลายปีไว้เหมือนเดิมตาม SKILL.md ส่วนหลักฐานโดรนถูกแยกไปอีกหน้าเพื่อไม่ให้ baseline ความละเอียดสูง 1 epoch ถูกอ่านปนกับ temporal change.</p>
        <div className="hero-status"><i/> Evidence stack QA: <strong>{manifest.evidence_layers ? 'PASSED' : '—'}</strong></div>
      </header>

      <section className="metric-grid" aria-label="ตัวเลขสำคัญ">
        <Metric label="พื้นที่แปลงหลัก" value={`${exec.project.primary_boundary_area_rai.toFixed(2)} ไร่`} note="PDD boundary" />
        <Metric label="กล้าไม้" value={exec.project.seedlings_total.toLocaleString('th-TH')} note="ปลูกสิ้นสุด 18 ต.ค. 2023" />
        <Metric label="Green fraction vs control" value={`+${optical.green_fraction_change_percentage_points.toFixed(2)} pp`} note="2026 เทียบ 2023 · สัญญาณเล็ก" tone="positive" />
        <Metric label="ขอบพืช project − control" value={`${veg.project_minus_control_change_m.toFixed(0)} m`} note="2023→2026 · ต่ำกว่า detection floor" />
      </section>

      <section className="panel timeline-panel">
        <div className="section-heading"><span>01</span><div><h2>Timeline slider</h2><small>ภาพย้อนหลังและช่วงก่อน–หลังปลูก</small></div></div>
        <div className="year-readout"><strong>{epoch.targetYear}</strong><div><span className={`period-badge ${post ? 'post' : pre ? 'pre' : 'historic'}`}>{post ? 'หลังปลูก' : pre ? 'ก่อนปลูก' : 'บริบทประวัติศาสตร์'}</span><small>ภาพจริง {epoch.actualYear}<br/>{epoch.sensor} · {epoch.dates.length} dates</small></div></div>
        <div className="timeline-slider-shell">
          <input className="timeline-slider" aria-label="เลือกปี" type="range" min="0" max={index.epochs.length - 1} step="1" value={yearIndex} onChange={(event) => setYearIndex(Number(event.target.value))}/>
          <div className="timeline-scale" aria-label="ปีข้อมูล">
            {index.epochs.map((item, itemIndex) => <button
              key={item.targetYear}
              type="button"
              className={`${itemIndex === yearIndex ? 'active' : ''} ${item.targetYear === 2023 ? 'intervention' : ''}`}
              style={{ left: `${(itemIndex / timelineDenominator) * 100}%` }}
              onClick={() => setYearIndex(itemIndex)}
              aria-label={`เลือกปี ${item.targetYear}`}
              aria-current={itemIndex === yearIndex ? 'true' : undefined}
            ><i/><span>{item.targetYear}</span></button>)}
          </div>
        </div>
        <label className="switch-row"><span><strong>Swipe ก่อน–หลัง</strong><small>ลากเส้นกลางแผนที่เพื่อเปรียบเทียบ</small></span><input type="checkbox" checked={compare} onChange={(event) => setCompare(event.target.checked)}/><i/></label>
        {compare && <div className="compare-readout"><span>ก่อน <b>{before.targetYear}</b></span><span>หลัง <b>{epoch.targetYear}</b></span></div>}
      </section>

      <section className="panel">
        <div className="section-heading"><span>02</span><div><h2>Evidence layers</h2><small>เปิด–ปิดข้อมูลแต่ละชั้น</small></div></div>
        <div className="layer-list">{layerOptions.map(([key, th, en]) => <label key={key}><input type="checkbox" checked={layers[key]} onChange={(event) => setLayers((current) => ({ ...current, [key]: event.target.checked }))}/><i className={`swatch ${key}`}/><span><strong>{th}</strong><small>{en}</small></span></label>)}</div>
        <label className="opacity">ความทึบภาพ <strong>{Math.round(opacity * 100)}%</strong><input type="range" min="0" max="1" step="0.05" value={opacity} onChange={(event) => setOpacity(Number(event.target.value))}/></label>
      </section>

      <section className="panel evidence-panel">
        <div className="section-heading"><span>03</span><div><h2>หลักฐานปัจจุบัน</h2><small>สรุปสั้น; รายละเอียดอยู่หน้า “ผล 2023–2026”</small></div></div>
        <article><span>การตั้งตัวของพืช</span><strong className="good">{statusLabel(exec.executive_decision.vegetation_establishment)}</strong><small>NDVI project−control +{optical.median_ndvi_project_minus_control_change_2026_vs_2023.toFixed(4)}; green fraction +{optical.green_fraction_change_percentage_points.toFixed(2)} pp</small></article>
        <article><span>ขอบพืชชายฝั่ง</span><strong>{statusLabel(exec.executive_decision.coastal_vegetation_edge_expansion)}</strong><small>project {veg.project_median_change_2023_2026_m.toFixed(0)} m · control {veg.control_median_change_2023_2026_m.toFixed(0)} m · uncertainty floor {veg.empirical_edge_instability_floor_m.toFixed(0)} m</small></article>
        <article><span>Waterline</span><strong className="warn">{statusLabel(exec.executive_decision.waterline_erosion_indicator)}</strong><small>contrast {water.baseline_three_scene_project_minus_control_2023_2026_m.toFixed(2)} → {water.tide_stage_single_scene_project_minus_control_2023_2026_m.toFixed(2)} m; shift {water.sensitivity_shift_m.toFixed(2)} m</small></article>
      </section>

      {selection ? <section className="panel transect-card">
        <div className="section-heading"><span>04</span><div><h2>Transect {selection.id}</h2><small>{selection.group === 'PROJECT_37_STC' ? 'หน้าแปลง 37-STC' : 'Control / reference'}</small></div></div>
        <div className="transect-stats"><div><span>2023</span><strong>{selection.edgeChanges['2023'] ?? '—'} m</strong></div><div><span>2026</span><strong>{selection.edgeChanges['2026'] ?? '—'} m</strong></div><div><span>threshold spread 2026</span><strong>{selection.thresholdSpread['2026'] ?? '—'} m</strong></div></div>
        <div className="mini-series">{Object.entries(selection.edgeChanges).filter(([year]) => Number(year) >= 2017).map(([year, value]) => <div key={year}><span>{year}</span><i style={{ height: `${Math.min(44, 8 + Math.abs(Number(value ?? 0)))}px` }}/><b>{value ?? '—'}</b></div>)}</div>
        <small className="click-hint">ค่าบวก = ขอบพืชออกทะเลเทียบปี 2023; ผลยังเป็น satellite screening</small>
      </section> : <section className="panel empty-card"><span>04</span><p>คลิก transect สีเหลืองหรือฟ้าบนแผนที่เพื่อดูการเปลี่ยนแปลงของขอบพืชรายแนว</p></section>}

      <footer>
        <strong>ข้อจำกัดสำคัญ</strong>
        <p>แนวขอบพืชเป็น spectral proxy จาก Sentinel-2 ไม่ใช่การสำรวจชนิดไม้ ส่วนขอบน้ำ–แผ่นดินใช้เป็นข้อมูลประกอบเท่านั้นเพราะไม่ผ่าน robustness test ต่อ tide/scene selection.</p>
        <span>สถานีน้ำอ้างอิง: เกาะปราบ · scene-level context บางปีเป็น partial MSL</span>
      </footer>
    </aside>

    <section className="map-stage">
      {compare
        ? <SwipeCompare epochs={index.epochs} beforeIndex={beforeIndex} afterIndex={yearIndex} before={before} after={epoch} layers={layers} opacity={opacity} sharedView={view} onView={setView} onTransect={onTransect} onBeforeChange={setBeforeIndex} onAfterChange={setYearIndex}/>
        : <MapPane epoch={epoch} label="SELECTED EPOCH" layers={layers} opacity={opacity} sharedView={view} onView={setView} onTransect={onTransect}/>
      }
      <div className="map-legend"><span><i className="project"/>37-STC vegetation edge</span><span><i className="control"/>control</span><span><i className="water"/>waterline · support</span></div>
    </section>
  </main>
}
