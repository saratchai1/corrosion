#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{path}: expected one match, found {count}: {old[:100]!r}')
    p.write_text(text.replace(old, new, 1), encoding='utf-8')


# App: add a real standalone drone page and explicit navigation targets.
replace_once(
    'web/src/App.tsx',
    "const MapPane = lazy(() => import('./MapPane'))\nconst ProjectDashboard = lazy(() => import('./ProjectDashboard'))",
    "const MapPane = lazy(() => import('./MapPane'))\nconst DroneBaselinePage = lazy(() => import('./DroneBaselinePage'))\nconst ProjectDashboard = lazy(() => import('./ProjectDashboard'))",
)
replace_once(
    'web/src/App.tsx',
    "const [page, setPage] = useState<'project' | 'tide' | 'coast'>('tide')",
    "const [page, setPage] = useState<'project' | 'tide' | 'drone' | 'coast'>('tide')\n  const [tideView, setTideView] = useState<'history' | 'current'>('history')",
)
replace_once(
    'web/src/App.tsx',
    "  if (error) return <main className=\"loading\">โหลดข้อมูลไม่สำเร็จ / Failed to load: {error}</main>",
    "  const openHistory = () => { setTideView('history'); setPage('tide') }\n  const openCurrent = () => { setTideView('current'); setPage('tide') }\n  const openDrone = () => setPage('drone')\n  const openProject = () => setPage('project')\n  const openCoast = () => setPage('coast')\n\n  if (error) return <main className=\"loading\">โหลดข้อมูลไม่สำเร็จ / Failed to load: {error}</main>",
)
replace_once(
    'web/src/App.tsx',
    "        <ProjectDashboard summary={projectSummary} onOpenCoast={() => setPage('coast')} />",
    "        <ProjectDashboard\n          summary={projectSummary}\n          onOpenHistory={openHistory}\n          onOpenCurrent={openCurrent}\n          onOpenDrone={openDrone}\n          onOpenCoast={openCoast}\n        />",
)
replace_once(
    'web/src/App.tsx',
    "      <TideAwareDashboard\n        summary={tideSummary}\n        onOpenProject={() => setPage('project')}\n        onOpenCoast={() => setPage('coast')}\n      />",
    "      <TideAwareDashboard\n        summary={tideSummary}\n        initialView={tideView}\n        onOpenDrone={openDrone}\n        onOpenProject={openProject}\n        onOpenCoast={openCoast}\n      />",
)
replace_once(
    'web/src/App.tsx',
    "  return (\n    <Suspense fallback={<ViewLoading label=\"กำลังเปิดแผนที่ดาวเทียม…\" />}>",
    "  if (page === 'drone') {\n    return (\n      <Suspense fallback={<ViewLoading label=\"กำลังเปิดภาพโดรนความละเอียดสูง…\" />}>\n        <DroneBaselinePage\n          onOpenHistory={openHistory}\n          onOpenCurrent={openCurrent}\n          onOpenProject={openProject}\n          onOpenCoast={openCoast}\n        />\n      </Suspense>\n    )\n  }\n\n  return (\n    <Suspense fallback={<ViewLoading label=\"กำลังเปิดแผนที่ดาวเทียม…\" />}>",
)
replace_once(
    'web/src/App.tsx',
    "          <div className=\"coast-view-tabs view-tabs\" role=\"tablist\" aria-label=\"เลือกมุมมอง\">\n            <button role=\"tab\" aria-selected=\"false\" onClick={() => setPage('project')}>รายงานผล 9 แปลง</button>\n            <button role=\"tab\" aria-selected=\"false\" onClick={() => setPage('tide')}>คุมระดับน้ำ</button>\n            <button className=\"active\" role=\"tab\" aria-selected=\"true\">แผนที่ดาวเทียม 10 ปี</button>\n          </div>",
    "          <div className=\"coast-view-tabs view-tabs\" role=\"tablist\" aria-label=\"เลือกมุมมอง\">\n            <button role=\"tab\" aria-selected=\"false\" onClick={openHistory}>หลักฐานย้อนหลัง</button>\n            <button role=\"tab\" aria-selected=\"false\" onClick={openCurrent}>ผล 2023–2026</button>\n            <button role=\"tab\" aria-selected=\"false\" onClick={openDrone}>ภาพโดรน HR</button>\n            <button role=\"tab\" aria-selected=\"false\" onClick={openProject}>รายงาน 9 แปลง</button>\n            <button className=\"active\" role=\"tab\" aria-selected=\"true\">แผนที่ 10 ปี</button>\n          </div>",
)
replace_once(
    'web/src/App.tsx',
    "<button type=\"button\" onClick={() => setPage('tide')}>เปิดรายงาน tide-aware</button>",
    "<button type=\"button\" onClick={openCurrent}>เปิดผล 2023–2026 แบบคุมระดับน้ำ</button>",
)

# History/current controller: restore old history-first page; do not inject drone into it.
replace_once(
    'web/src/TideAwareDashboard.tsx',
    "import DroneBaselineInjector, {\n  type DroneBaselineSummary,\n} from './DroneBaselineInjector'\n",
    "",
)
replace_once(
    'web/src/TideAwareDashboard.tsx',
    "type Props = {\n  summary: TideAwareSummary\n  onOpenProject: () => void\n  onOpenCoast: () => void\n}\n\nexport default function TideAwareDashboard({ summary, onOpenProject, onOpenCoast }: Props) {\n  const [view, setView] = useState<'history' | 'current'>('history')",
    "type Props = {\n  summary: TideAwareSummary\n  initialView?: 'history' | 'current'\n  onOpenDrone: () => void\n  onOpenProject: () => void\n  onOpenCoast: () => void\n}\n\nexport default function TideAwareDashboard({\n  summary,\n  initialView = 'history',\n  onOpenDrone,\n  onOpenProject,\n  onOpenCoast,\n}: Props) {\n  const [view, setView] = useState<'history' | 'current'>(initialView)",
)
replace_once(
    'web/src/TideAwareDashboard.tsx',
    "  const [planting, setPlanting] = useState<PlantingAwareSummary | null>(null)\n  const [drone, setDrone] = useState<DroneBaselineSummary | null>(null)",
    "  const [planting, setPlanting] = useState<PlantingAwareSummary | null>(null)\n\n  useEffect(() => {\n    setView(initialView)\n  }, [initialView])",
)
old_drone_effect = """  useEffect(() => {
    let active = true
    fetch('data/project_drone_orthomosaic/summary.json')
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        return response.json()
      })
      .then((value: unknown) => {
        if (active) setDrone(value as DroneBaselineSummary)
      })
      .catch(() => {
        if (active) setDrone(null)
      })
    return () => {
      active = false
    }
  }, [])

"""
replace_once('web/src/TideAwareDashboard.tsx', old_drone_effect, '')
replace_once(
    'web/src/TideAwareDashboard.tsx',
    "        <TideAwareOverview\n          summary={summary}\n          onOpenProject={onOpenProject}\n          onOpenCoast={onOpenCoast}\n        />",
    "        <TideAwareOverview\n          summary={summary}\n          onOpenHistory={() => setView('history')}\n          onOpenDrone={onOpenDrone}\n          onOpenProject={onOpenProject}\n          onOpenCoast={onOpenCoast}\n        />",
)
replace_once(
    'web/src/TideAwareDashboard.tsx',
    "        onOpenCurrent={() => setView('current')}\n        onOpenProject={onOpenProject}",
    "        onOpenCurrent={() => setView('current')}\n        onOpenDrone={onOpenDrone}\n        onOpenProject={onOpenProject}",
)
replace_once(
    'web/src/TideAwareDashboard.tsx',
    "      {planting && <PlantingEvidenceInjector summary={planting} />}\n      {drone && <DroneBaselineInjector summary={drone} />}\n      <PlotOverlayInjector",
    "      {planting && <PlantingEvidenceInjector summary={planting} />}\n      <PlotOverlayInjector",
)

# Old multispectral history page remains the primary page; only add the new destination to its nav.
replace_once(
    'web/src/PreplantingHistoryDashboardV2.tsx',
    "  onOpenCurrent: () => void\n  onOpenProject: () => void",
    "  onOpenCurrent: () => void\n  onOpenDrone: () => void\n  onOpenProject: () => void",
)
replace_once(
    'web/src/PreplantingHistoryDashboardV2.tsx',
    "export default function PreplantingHistoryDashboardV2({ history, onOpenCurrent, onOpenProject, onOpenCoast }: Props)",
    "export default function PreplantingHistoryDashboardV2({ history, onOpenCurrent, onOpenDrone, onOpenProject, onOpenCoast }: Props)",
)
replace_once(
    'web/src/PreplantingHistoryDashboardV2.tsx',
    "<div><button className=\"active\">ก่อนปลูกเคยถอยไหม</button><button onClick={onOpenCurrent}>ผล 2023–2026</button><button onClick={onOpenProject}>รายงาน 9 แปลง</button><button onClick={onOpenCoast}>แผนที่ 10 ปี</button></div>",
    "<div><button className=\"active\">หลักฐานย้อนหลัง</button><button onClick={onOpenCurrent}>ผล 2023–2026</button><button onClick={onOpenDrone}>ภาพโดรน HR</button><button onClick={onOpenProject}>รายงาน 9 แปลง</button><button onClick={onOpenCoast}>แผนที่ 10 ปี</button></div>",
)

# Current tide-aware page: same five destinations, same order.
replace_once(
    'web/src/TideAwareOverview.tsx',
    "type Props = {\n  summary: TideAwareSummary\n  onOpenProject: () => void\n  onOpenCoast: () => void\n}",
    "type Props = {\n  summary: TideAwareSummary\n  onOpenHistory: () => void\n  onOpenDrone: () => void\n  onOpenProject: () => void\n  onOpenCoast: () => void\n}",
)
replace_once(
    'web/src/TideAwareOverview.tsx',
    "export default function TideAwareOverview({ summary, onOpenProject, onOpenCoast }: Props)",
    "export default function TideAwareOverview({ summary, onOpenHistory, onOpenDrone, onOpenProject, onOpenCoast }: Props)",
)
replace_once(
    'web/src/TideAwareOverview.tsx',
    "          <button role=\"tab\" aria-selected=\"false\" onClick={onOpenProject}>รายงาน 9 แปลง</button>\n          <button className=\"active\" role=\"tab\" aria-selected=\"true\">ภาพก่อน–หลัง</button>\n          <button role=\"tab\" aria-selected=\"false\" onClick={onOpenCoast}>แผนที่ 10 ปี</button>",
    "          <button role=\"tab\" aria-selected=\"false\" onClick={onOpenHistory}>หลักฐานย้อนหลัง</button>\n          <button className=\"active\" role=\"tab\" aria-selected=\"true\">ผล 2023–2026</button>\n          <button role=\"tab\" aria-selected=\"false\" onClick={onOpenDrone}>ภาพโดรน HR</button>\n          <button role=\"tab\" aria-selected=\"false\" onClick={onOpenProject}>รายงาน 9 แปลง</button>\n          <button role=\"tab\" aria-selected=\"false\" onClick={onOpenCoast}>แผนที่ 10 ปี</button>",
)

# Project page: make navigation no longer a dead-end with only two choices.
replace_once(
    'web/src/ProjectDashboard.tsx',
    "type Props = {\n  summary: ProjectImpactSummary\n  onOpenCoast: () => void\n}",
    "type Props = {\n  summary: ProjectImpactSummary\n  onOpenHistory: () => void\n  onOpenCurrent: () => void\n  onOpenDrone: () => void\n  onOpenCoast: () => void\n}",
)
replace_once(
    'web/src/ProjectDashboard.tsx',
    "export default function ProjectDashboard({ summary, onOpenCoast }: Props)",
    "export default function ProjectDashboard({ summary, onOpenHistory, onOpenCurrent, onOpenDrone, onOpenCoast }: Props)",
)
replace_once(
    'web/src/ProjectDashboard.tsx',
    "          <button className=\"active\" role=\"tab\" aria-selected=\"true\">รายงาน 9 แปลง</button>\n          <button role=\"tab\" aria-selected=\"false\" onClick={onOpenCoast}>แผนที่ดาวเทียม 10 ปี</button>",
    "          <button role=\"tab\" aria-selected=\"false\" onClick={onOpenHistory}>หลักฐานย้อนหลัง</button>\n          <button role=\"tab\" aria-selected=\"false\" onClick={onOpenCurrent}>ผล 2023–2026</button>\n          <button role=\"tab\" aria-selected=\"false\" onClick={onOpenDrone}>ภาพโดรน HR</button>\n          <button className=\"active\" role=\"tab\" aria-selected=\"true\">รายงาน 9 แปลง</button>\n          <button role=\"tab\" aria-selected=\"false\" onClick={onOpenCoast}>แผนที่ 10 ปี</button>",
)

Path('web/src/DroneBaselinePage.tsx').write_text('''import { useEffect, useState } from 'react'\nimport DroneBaselineInjector, {\n  type DroneBaselineSummary,\n} from './DroneBaselineInjector'\nimport './preplantingSpectral.css'\n\ntype Props = {\n  onOpenHistory: () => void\n  onOpenCurrent: () => void\n  onOpenProject: () => void\n  onOpenCoast: () => void\n}\n\nexport default function DroneBaselinePage({\n  onOpenHistory,\n  onOpenCurrent,\n  onOpenProject,\n  onOpenCoast,\n}: Props) {\n  const [summary, setSummary] = useState<DroneBaselineSummary | null>(null)\n  const [error, setError] = useState<string | null>(null)\n\n  useEffect(() => {\n    let active = true\n    fetch('data/project_drone_orthomosaic/summary.json')\n      .then((response) => {\n        if (!response.ok) throw new Error(`HTTP ${response.status}`)\n        return response.json()\n      })\n      .then((value: unknown) => {\n        if (active) setSummary(value as DroneBaselineSummary)\n      })\n      .catch((reason: unknown) => {\n        if (active) setError(reason instanceof Error ? reason.message : String(reason))\n      })\n    return () => {\n      active = false\n    }\n  }, [])\n\n  return (\n    <main className="spectral-shell drone-standalone-page">\n      <nav className="spectral-nav">\n        <div><span>สมุทรสงคราม</span><strong>Coastal Evidence</strong></div>\n        <div>\n          <button onClick={onOpenHistory}>หลักฐานย้อนหลัง</button>\n          <button onClick={onOpenCurrent}>ผล 2023–2026</button>\n          <button className="active">ภาพโดรน HR</button>\n          <button onClick={onOpenProject}>รายงาน 9 แปลง</button>\n          <button onClick={onOpenCoast}>แผนที่ 10 ปี</button>\n        </div>\n      </nav>\n\n      <section className="drone-page-context">\n        <span>HIGH-RESOLUTION REVIEW · SEPARATE EVIDENCE PAGE</span>\n        <h1>ภาพโดรนความละเอียดสูง</h1>\n        <p>หน้านี้แยกจากสไลเดอร์ดาวเทียมย้อนหลังโดยตั้งใจ เพื่อไม่ให้ baseline โดรน 1 epoch ถูกอ่านปนกับการเปรียบเทียบหลายปีของ Sentinel-2</p>\n      </section>\n\n      {error && <section className="drone-page-status">โหลดข้อมูลโดรนไม่สำเร็จ: {error}</section>}\n      {!summary && !error && <section className="drone-page-status">กำลังเปิดภาพโดรนทั้ง 9 แปลง…</section>}\n      {summary && (\n        <section className="drone-standalone-content">\n          <DroneBaselineInjector summary={summary} />\n          <div className="spectral-compare drone-portal-marker" aria-hidden="true" />\n        </section>\n      )}\n    </main>\n  )\n}\n''', encoding='utf-8')

css_path = Path('web/src/droneBaseline.css')
css = css_path.read_text(encoding='utf-8')
addition = '''\n\n/* Standalone high-resolution page: keep drone evidence separate from the history slider. */\n.drone-page-context {\n  max-width: 1500px;\n  margin: 24px auto 0;\n  padding: 24px 28px;\n  border: 1px solid rgba(121, 178, 167, 0.28);\n  background: rgba(8, 36, 36, 0.72);\n}\n.drone-page-context > span {\n  color: #8dcbbb;\n  font-size: 11px;\n  letter-spacing: .12em;\n}\n.drone-page-context h1 {\n  margin: 8px 0 6px;\n  font-size: clamp(28px, 3vw, 46px);\n}\n.drone-page-context p {\n  margin: 0;\n  max-width: 980px;\n  color: #aac0bc;\n  line-height: 1.7;\n}\n.drone-standalone-content {\n  max-width: 1500px;\n  margin: 16px auto 48px;\n}\n.drone-portal-marker {\n  display: none !important;\n}\n.drone-page-status {\n  max-width: 1500px;\n  margin: 16px auto;\n  padding: 28px;\n  border: 1px solid rgba(121, 178, 167, 0.22);\n  color: #b8cfca;\n}\n'''
if 'Standalone high-resolution page' not in css:
    css_path.write_text(css + addition, encoding='utf-8')

print('UX separation patch applied')
