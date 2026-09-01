import type { DataIndex, EvidenceManifest, ExecutiveSummary } from './types'

type Props = { index: DataIndex; exec: ExecutiveSummary; manifest: EvidenceManifest }

export default function CurrentEvidencePage({ index, exec, manifest }: Props) {
  const optical = exec.key_numbers.optical_establishment
  const vegetation = exec.key_numbers.coastal_vegetation_edge
  const water = exec.key_numbers.waterline_sensitivity
  const first = index.epochs[0]
  const latest = index.epochs[index.epochs.length - 1]

  return (
    <main className="document-page">
      <section className="document-hero">
        <span>CURRENT EVIDENCE · 2023–2026</span>
        <h1>ผลล่าสุดของ 37-STC</h1>
        <p>หน้านี้แยก interpretation ออกจากหน้าประวัติหลายปี เพื่อให้เห็นชัดว่าอะไรตรวจพบแล้ว อะไรยังเป็นเพียง supporting evidence และอะไรยังห้ามเคลม.</p>
      </section>

      <section className="document-metrics four">
        <article><span>Green fraction vs control</span><strong>+{optical.green_fraction_change_percentage_points.toFixed(2)} pp</strong><small>2026 เทียบ 2023 · small positive monitoring signal</small></article>
        <article><span>Median NDVI vs control</span><strong>+{optical.median_ndvi_project_minus_control_change_2026_vs_2023.toFixed(4)}</strong><small>ขนาดเล็กเมื่อเทียบ scene variability</small></article>
        <article><span>Vegetation edge project − control</span><strong>{vegetation.project_minus_control_change_m.toFixed(0)} m</strong><small>ต่ำกว่า empirical instability floor {vegetation.empirical_edge_instability_floor_m.toFixed(0)} m</small></article>
        <article className="warning"><span>Waterline sensitivity shift</span><strong>{water.sensitivity_shift_m.toFixed(2)} m</strong><small>{water.sign_reversal ? 'ผลกลับเครื่องหมายเมื่อเปลี่ยน scene/tide selection' : 'sensitivity ยังต้องตรวจ'}</small></article>
      </section>

      <section className="evidence-grid">
        <article className="evidence-card good"><span>01 · Satellite history</span><h2>{first?.targetYear}–{latest?.targetYear}</h2><p>{index.epochs.length} epochs พร้อม annual imagery และ vegetation-edge screening.</p></article>
        <article className="evidence-card"><span>02 · Tide-aware screening</span><h2>{index.tide_status.replaceAll('_', ' ')}</h2><p>มี scene-level tide context บางปี แต่ยังไม่ใช่ full tide normalization.</p></article>
        <article className="evidence-card"><span>03 · Planting timing</span><h2>18 ต.ค. 2023</h2><p>ใช้วันปลูกสิ้นสุดเป็น representative intervention date ตามการยืนยันของโครงการ; ไม่ได้อนุมานวันเริ่มปลูก.</p></article>
        <article className="evidence-card good"><span>04 · Control</span><h2>Known intervention excluded</h2><p>พื้นที่ control ที่เลือกได้รับการยืนยันว่าไม่มี known planting/coastal intervention แต่ physical setting equivalence ยังต้อง field-check.</p></article>
        <article className="evidence-card pending"><span>05 · UAV / field</span><h2>Baseline available · validation pending</h2><p>มี orthomosaic 37-STC ใน Drive แล้ว แต่ raw GeoTIFF metadata/CRS/GSD ยังต้องตรวจ ก่อนใช้ cross-sensor alignment หรือยกระดับ edge validation.</p></article>
      </section>

      <section className="decision-banner">
        <span>EROSION EFFECT</span>
        <strong>NOT DEMONSTRATED</strong>
        <p>{manifest.causal_erosion_reduction_claim.replaceAll('_', ' ')}</p>
      </section>

      <section className="two-column-copy">
        <article><h2>ข้อมูลรองรับ</h2><ul>{exec.what_the_data_supports.map((item) => <li key={item}>{item}</li>)}</ul></article>
        <article><h2>ข้อมูลยังไม่รองรับ</h2><ul>{exec.what_the_data_do_not_support.map((item) => <li key={item}>{item}</li>)}</ul></article>
      </section>
    </main>
  )
}
