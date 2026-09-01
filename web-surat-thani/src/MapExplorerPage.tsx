import { useCallback, useState } from 'react'
import MapPane from './MapPane'
import type { DataIndex, LayerVisibility, TransectSelection, ViewState } from './types'

const initialView: ViewState = { center: [99.231, 9.343], zoom: 12.2, bearing: 0, pitch: 0 }

type Props = { index: DataIndex }

export default function MapExplorerPage({ index }: Props) {
  const [yearIndex, setYearIndex] = useState(index.epochs.length - 1)
  const [view, setView] = useState(initialView)
  const [selection, setSelection] = useState<TransectSelection | null>(null)
  const [layers, setLayers] = useState<LayerVisibility>({ imagery: true, vegetation: false, waterline: false, vegetationEdge: true, projectBoundary: true, controls: true })
  const onTransect = useCallback((value: TransectSelection) => setSelection(value), [])
  const epoch = index.epochs[yearIndex]
  if (!epoch) return null

  return (
    <main className="map-explorer-page">
      <aside className="map-explorer-sidebar">
        <span className="eyebrow">MULTI-YEAR SPATIAL EXPLORER</span>
        <h1>แผนที่หลายปี</h1>
        <p>เลือกปีและ evidence layer เพื่อดูตำแหน่งจริงบนแผนที่ หน้านี้เป็น spatial explorer และไม่แทนหน้าประวัติ before/after slider.</p>
        <label className="map-year-select">ปีข้อมูล<select value={yearIndex} onChange={(event) => setYearIndex(Number(event.target.value))}>{index.epochs.map((item, itemIndex) => <option key={item.targetYear} value={itemIndex}>{item.targetYear} · ภาพจริง {item.actualYear}</option>)}</select></label>
        <div className="map-layer-toggles">
          {([
            ['imagery', 'ภาพดาวเทียม'],
            ['vegetationEdge', 'ขอบพืชชายฝั่ง'],
            ['controls', 'Control'],
            ['projectBoundary', '37-STC'],
            ['vegetation', 'Vegetation proxy'],
            ['waterline', 'Waterline · support'],
          ] as const).map(([key, label]) => <label key={key}><input type="checkbox" checked={layers[key]} onChange={(event) => setLayers((current) => ({ ...current, [key]: event.target.checked }))}/><span>{label}</span></label>)}
        </div>
        {selection && <article className="map-selection"><span>Transect</span><strong>{selection.id}</strong><small>{selection.group} · confidence {selection.confidence}</small></article>}
      </aside>
      <section className="map-explorer-stage"><MapPane epoch={epoch} label="MAP EXPLORER" layers={layers} opacity={0.94} sharedView={view} onView={setView} onTransect={onTransect}/></section>
    </main>
  )
}
