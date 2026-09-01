#!/usr/bin/env python3
import re
from pathlib import Path

src = Path('web/src')
history = (src / 'PreplantingHistoryDashboardV2.tsx').read_text(encoding='utf-8')
controller = (src / 'TideAwareDashboard.tsx').read_text(encoding='utf-8')
overlay = (src / 'PlotOverlayInjector.tsx').read_text(encoding='utf-8')
app = (src / 'App.tsx').read_text(encoding='utf-8')
drone = (src / 'DroneBaselinePage.tsx').read_text(encoding='utf-8')

for token in [
    "const MODE_ORDER: ModeKey[] = ['rgb', 'false_vegetation', 'ndvi', 'mndwi', 'swir']",
    '2020 → 2023', '2020 → 2026', '2023 → 2026',
    'spectral-swipe-stage', 'ภาพก่อน', 'ภาพหลัง',
]:
    assert token in history, token
for token in ['MAX_ZOOM = 3', 'ZOOM_STEP = 0.25', 'spectral-pan-hint', 'onPanPointerDown']:
    assert token in overlay, token
assert 'DroneBaselineInjector' not in controller

assert "'drone'" in app
assert "lazy(() => import('./DroneBaselinePage'))" in app
assert 'ภาพโดรน HR' in drone
assert Path('web/public/data/project_drone_orthomosaic/summary.json').exists()
assert len(list(Path('web/public/data/project_drone_orthomosaic/previews').glob('*.webp'))) == 9

nav_labels = ['หลักฐานย้อนหลัง', 'ผล 2023–2026', 'ภาพโดรน HR', 'รายงาน 9 แปลง', 'แผนที่ 10 ปี']
for path in [
    src / 'PreplantingHistoryDashboardV2.tsx',
    src / 'TideAwareOverview.tsx',
    src / 'ProjectDashboard.tsx',
    src / 'DroneBaselinePage.tsx',
]:
    text = path.read_text(encoding='utf-8')
    positions = [text.find(label) for label in nav_labels]
    assert all(position >= 0 for position in positions), (path, positions)
    assert positions == sorted(positions), (path, positions)

# App contains labels elsewhere too, so inspect the coast navigation block itself.
start = app.index('<div className="coast-view-tabs view-tabs"')
end = app.index('</div>', start)
coast_nav = app[start:end]
positions = [coast_nav.find(label) for label in nav_labels]
assert all(position >= 0 for position in positions), positions
assert positions == sorted(positions), positions

missing = []
pattern = re.compile(r'''href=["'](data/[^"'#?]+)''')
for path in src.glob('*.tsx'):
    text = path.read_text(encoding='utf-8')
    for href in pattern.findall(text):
        public = Path('web/public') / href
        if not public.exists():
            missing.append((path.name, href))
    assert 'href="#"' not in text, path
assert not missing, missing

print('Navigation + evidence link audit: PASS')
