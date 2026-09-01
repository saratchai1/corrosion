#!/usr/bin/env python3
"""Generate same-extent historical satellite RGB assets for the 37-STC Drone page.

Uses the already-published georeferenced web imagery and the verified Drone
WGS84 envelope. No raw TIFF is read or committed by this script. If real
multispectral products have already been published, their catalog metadata is
preserved so an RGB rebuild cannot downgrade the page back to display filters.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image

ROOT = Path('web-surat-thani/public/data/surat_thani')
INDEX = ROOT / 'imagery_index.json'
MANIFEST = ROOT / 'drone/drone_manifest.json'
OUT_DIR = ROOT / 'drone/multiyear'
CATALOG = ROOT / 'drone/compare_catalog.json'
SPECTRAL_KEYS = ('visuals', 'spectralStatus', 'spectralDatesUsed', 'spectralItemIds', 'supportedModes')


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


def bounds_from_manifest(manifest: dict[str, Any]) -> tuple[dict[str, float], int, int]:
    compare = manifest.get('same_extent_compare') or {}
    bounds = compare.get('bounds_wgs84')
    if not bounds:
        raise RuntimeError('same_extent_compare.bounds_wgs84 missing from drone_manifest.json')
    width = int(compare.get('width_px') or 1800)
    height = int(compare.get('height_px') or 1015)
    return bounds, width, height


def render(source: Path, epoch: dict[str, Any], target: dict[str, float], out: Path, size: tuple[int, int]) -> None:
    coords = epoch['imageCoordinates']
    xs = [float(item[0]) for item in coords]
    ys = [float(item[1]) for item in coords]
    left, right = min(xs), max(xs)
    bottom, top = min(ys), max(ys)

    if not (target['left'] >= left and target['right'] <= right and target['bottom'] >= bottom and target['top'] <= top):
        raise RuntimeError(f"Target Drone bounds are not contained by {epoch['targetYear']} imagery")

    with Image.open(source) as image:
        image = image.convert('RGB')
        w, h = image.size
        x0 = (target['left'] - left) / (right - left) * w
        x1 = (target['right'] - left) / (right - left) * w
        y0 = (top - target['top']) / (top - bottom) * h
        y1 = (top - target['bottom']) / (top - bottom) * h
        sampled = image.transform(size, Image.Transform.EXTENT, (x0, y0, x1, y1), resample=Image.Resampling.BILINEAR)
        out.parent.mkdir(parents=True, exist_ok=True)
        sampled.save(out, format='WEBP', quality=90, method=6)


def family(epoch: dict[str, Any]) -> str:
    dataset = str(epoch.get('dataset', '')).lower()
    if 'sentinel' in dataset or 'sentinel' in str(epoch.get('sensor', '')).lower():
        return 'Sentinel-2'
    if 'landsat' in dataset or 'landsat' in str(epoch.get('sensor', '')).lower():
        return 'Landsat'
    return str(epoch.get('sensor') or 'Satellite')


def period(year: int) -> str:
    if year <= 2010:
        return 'historical_context'
    if year <= 2023:
        return 'pre_planting'
    return 'post_planting'


def preserve_spectral(new_catalog: dict[str, Any], previous: dict[str, Any] | None) -> None:
    if not previous:
        return
    old_left = {item.get('id'): item for item in previous.get('leftChoices', [])}
    old_right = {item.get('id'): item for item in previous.get('rightChoices', [])}
    for item in new_catalog.get('leftChoices', []):
        old = old_left.get(item.get('id')) or {}
        for key in SPECTRAL_KEYS:
            if key in old:
                item[key] = old[key]
    for item in new_catalog.get('rightChoices', []):
        old = old_right.get(item.get('id')) or {}
        for key in SPECTRAL_KEYS:
            if key in old:
                item[key] = old[key]
    for key in ('spectralModes', 'spectral_generation'):
        if key in previous:
            new_catalog[key] = previous[key]
    if previous.get('spectralModes'):
        new_catalog['visual_mode_guard'] = previous.get('visual_mode_guard', new_catalog['visual_mode_guard'])


def main() -> int:
    index = load(INDEX)
    manifest = load(MANIFEST)
    previous = load(CATALOG) if CATALOG.is_file() else None
    bounds, width, height = bounds_from_manifest(manifest)
    choices: list[dict[str, Any]] = []

    for epoch in index.get('epochs', []):
        target_year = int(epoch['targetYear'])
        source = ROOT / epoch['image']
        if not source.is_file():
            raise RuntimeError(f'Missing imagery source: {source}')
        out = OUT_DIR / f'satellite_{target_year}_same_extent.webp'
        render(source, epoch, bounds, out, (width, height))
        sensor_family = family(epoch)
        actual = int(epoch.get('actualYear', target_year))
        actual_suffix = '' if actual == target_year else f' · ภาพจริง {actual}'
        choices.append({
            'id': f'satellite-{target_year}',
            'targetYear': target_year,
            'actualYear': actual,
            'label': f'{sensor_family} {target_year}{actual_suffix}',
            'sensor': str(epoch.get('sensor') or sensor_family),
            'dates': epoch.get('dates', []),
            'resolutionM': epoch.get('resolutionM'),
            'asset': f'data/surat_thani/drone/multiyear/{out.name}',
            'period': period(target_year),
        })

    if not choices:
        raise RuntimeError('No imagery epochs found')

    target_ids = {item['targetYear']: item['id'] for item in choices}
    default_left = target_ids.get(2023, choices[-2]['id'] if len(choices) > 1 else choices[0]['id'])
    satellite_2026 = next((item for item in choices if item['targetYear'] == 2026), choices[-1])
    compare = manifest['same_extent_compare']

    catalog = {
        'title': 'Historical Satellite ↔ Current Reference',
        'status': 'AVAILABLE_MULTIPLE_EPOCHS_SAME_EXTENT',
        'bounds_wgs84': bounds,
        'width_px': width,
        'height_px': height,
        'defaultLeftId': default_left,
        'defaultRightId': 'drone',
        'leftChoices': choices,
        'rightChoices': [
            {
                'id': 'drone',
                'label': 'Drone HR',
                'asset': compare['drone_asset'],
                'note': f"Orthomosaic · {manifest['qa'].get('mean_gsd_cm', 0):.3f} cm/px",
            },
            {
                'id': 'satellite-2026',
                'label': 'Sentinel-2 2026',
                'asset': satellite_2026['asset'],
                'note': 'ดาวเทียมปีปัจจุบัน · same extent',
            },
        ],
        'visual_mode_guard': 'RGB same-extent assets are generated from the published annual imagery.',
        'generation': {
            'script': 'scripts/publish_surat_thani_multiyear_compare.py',
            'source': 'web-surat-thani/public/data/surat_thani/imagery_index.json',
            'method': 'crop/resample each existing georeferenced web image to the verified raw-drone WGS84 envelope and common pixel dimensions',
        },
    }
    preserve_spectral(catalog, previous)
    CATALOG.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': 'PASS', 'epochs': [item['targetYear'] for item in choices], 'catalog': str(CATALOG), 'preserved_spectral': bool(catalog.get('spectralModes'))}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
