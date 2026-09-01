import type { DataIndex, EvidenceManifest, ExecutiveSummary } from './types'

type Props = { index: DataIndex; exec: ExecutiveSummary; manifest: EvidenceManifest }

export default function ReportPage({ index, exec, manifest }: Props) {
  const latest = index.epochs[index.epochs.length - 1]
  const optical = exec.key_numbers.optical_establishment
  const vegetation = exec.key_numbers.coastal_vegetation_edge

  return (
    <main className="document-page report-page">
      <section className="document-hero">
        <span>37-STC · EXECUTIVE REPORT</span>
        <h1>สถานะหลักฐานสุราษฎร์ธานี</h1>
        <p>สรุปจาก evidence stack ที่ผ่าน QA โดยแยกสิ่งที่ตรวจพบจากข้อกล่าวที่ยังต้องการ UAV/field และ stable geomorphic edge.</p>
      </section>

      <section className="report-summary">
        <article><span>ช่วงข้อมูล</span><strong>{index.epochs[0]?.targetYear}–{latest?.targetYear}</strong><small>{index.epochs.length} epochs</small></article>
        <article><span>พื้นที่วิเคราะห์หลัก</span><strong>{exec.project.primary_boundary_area_rai.toFixed(2)} ไร่</strong><small>{exec.project.plot_code}</small></article>
        <article><span>Vegetation establishment</span><strong>+{optical.green_fraction_change_percentage_points.toFixed(2)} pp</strong><small>project − control · 2023→2026</small></article>
        <article><span>Vegetation edge</span><strong>{vegetation.project_minus_control_change_m.toFixed(0)} m</strong><small>ยังต่ำกว่า detection floor</small></article>
      </section>

      <section className="report-conclusion">
        <span>CONCLUSION</span>
        <h2>พบสัญญาณการตั้งตัวของพืชเล็กน้อย แต่ยังไม่แสดงผลลดการกัดเซาะเชิงสาเหตุ</h2>
        <p>Waterline ถูกลดบทบาทเป็น supporting context หลัง sensitivity test กลับเครื่องหมายเมื่อเปลี่ยน tide/scene selection ขณะที่ vegetation edge ยังไม่แสดงการขยายที่ใหญ่กว่าความไม่แน่นอนเชิงตำแหน่ง.</p>
      </section>

      <section className="two-column-copy">
        <article><h2>สิ่งที่ข้อมูลรองรับ</h2><ul>{exec.what_the_data_supports.map((item) => <li key={item}>{item}</li>)}</ul></article>
        <article><h2>สิ่งที่ข้อมูลไม่รองรับ</h2><ul>{exec.what_the_data_do_not_support.map((item) => <li key={item}>{item}</li>)}</ul></article>
      </section>

      <section className="hard-gates">
        <span>REMAINING HARD GATES</span>
        <ol>{manifest.remaining_hard_gates.map((item) => <li key={item}>{item}</li>)}</ol>
      </section>
    </main>
  )
}
