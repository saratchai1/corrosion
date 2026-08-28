import type { TransectSelection } from './types'

const labels: Record<string, string> = {
  apparent_erosion: 'ถอยร่นที่ปรากฏ / apparent erosion',
  apparent_accretion: 'งอกเพิ่มที่ปรากฏ / apparent accretion',
  stable: 'คงที่ในช่วงความละเอียด / stable',
  insufficient_data: 'ข้อมูลไม่เพียงพอ',
}

export default function TransectChart({ selection }: { selection: TransectSelection }) {
  const values = Object.entries(selection.positions)
    .filter((entry): entry is [string, number] => entry[1] !== null)
    .map(([year, value]) => ({ year: Number(year), value }))
    .sort((a, b) => a.year - b.year)
  const width = 330
  const height = 150
  const padding = { left: 42, right: 14, top: 16, bottom: 30 }
  const years = values.map((item) => item.year)
  const positions = values.map((item) => item.value)
  const minYear = Math.min(...years)
  const maxYear = Math.max(...years)
  const extent = Math.max(40, ...positions.map((value) => Math.abs(value)))
  const x = (year: number) =>
    padding.left + ((year - minYear) / Math.max(1, maxYear - minYear)) * (width - padding.left - padding.right)
  const y = (value: number) =>
    padding.top + ((extent - value) / (extent * 2)) * (height - padding.top - padding.bottom)
  const path = values.map((item, index) => `${index ? 'L' : 'M'} ${x(item.year)} ${y(item.value)}`).join(' ')

  return (
    <section className="chart-card" aria-label={`Transect ${selection.id}`}>
      <div className="chart-title">
        <div>
          <span className="eyebrow">SELECTED TRANSECT</span>
          <strong>{selection.id}</strong>
        </div>
        <span className={`status-dot ${selection.classification}`} />
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Boundary position through time">
        <line x1={padding.left} y1={y(0)} x2={width - padding.right} y2={y(0)} className="zero-line" />
        <text x="3" y={y(extent) + 4}>+{Math.round(extent)} m</text>
        <text x="11" y={y(0) + 4}>0 m</text>
        <text x="3" y={y(-extent) + 4}>−{Math.round(extent)} m</text>
        <path d={path} className="chart-path" />
        {values.map((item) => (
          <g key={item.year}>
            <circle cx={x(item.year)} cy={y(item.value)} r="4" />
            <text x={x(item.year)} y={height - 9} textAnchor="middle">{String(item.year).slice(2)}</text>
          </g>
        ))}
      </svg>
      <div className="chart-stats">
        <div><span>สุทธิ / net</span><strong>{selection.netChange?.toFixed(1) ?? '—'} m</strong></div>
        <div><span>อัตรา / rate</span><strong>{selection.rate?.toFixed(1) ?? '—'} m/yr</strong></div>
        <div><span>confidence</span><strong>{selection.confidence}</strong></div>
      </div>
      <p className="classification">{labels[selection.classification] ?? selection.classification}</p>
    </section>
  )
}
