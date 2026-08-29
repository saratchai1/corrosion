#!/usr/bin/env python3
"""Generate shore-normal transects from a smoothed coastal baseline.

Instead of convex hull, we use the extracted shoreline directly,
smooth it to suppress pixel noise, and generate perpendicular transects.
"""
import geopandas as gpd
from shapely.geometry import LineString, MultiLineString
from shapely.ops import linemerge
import numpy as np
from pathlib import Path

def smooth_line(line: LineString, tolerance: float = 100) -> LineString:
    """Simplify (smooth) a line using Douglas-Peucker with moderate tolerance."""
    return line.simplify(tolerance, preserve_topology=True)

def create_transects(baseline: LineString, spacing: float = 100, length: float = 2000):
    """Generate transects perpendicular to local baseline direction."""
    transects = []
    ids = []
    distances = np.arange(0, baseline.length, spacing)
    
    for i, d in enumerate(distances):
        pt = baseline.interpolate(d)
        
        # Use a small offset to compute local tangent direction
        d_before = max(0, d - 10)
        d_after = min(baseline.length, d + 10)
        pt_before = baseline.interpolate(d_before)
        pt_after = baseline.interpolate(d_after)
        
        dx = pt_after.x - pt_before.x
        dy = pt_after.y - pt_before.y
        
        if dx == 0 and dy == 0:
            continue
        
        # Perpendicular direction
        angle = np.arctan2(dy, dx)
        perp = angle + np.pi / 2
        
        half = length / 2
        x1 = pt.x - half * np.cos(perp)
        y1 = pt.y - half * np.sin(perp)
        x2 = pt.x + half * np.cos(perp)
        y2 = pt.y + half * np.sin(perp)
        
        transects.append(LineString([(x1, y1), (x2, y2)]))
        ids.append(f"TR_{i:04d}")
    
    return ids, transects


def main():
    # Load the best shoreline extraction
    shoreline_path = "data/analysis/rayong/shorelines/2025-02-09.geojson"
    sl = gpd.read_file(shoreline_path)
    sl_proj = sl.to_crs(epsg=32647)
    
    geom = sl_proj.geometry.iloc[0]
    
    # Extract individual LineStrings
    if geom.geom_type == 'MultiLineString':
        lines = list(geom.geoms)
    else:
        lines = [geom]
    
    # Sort by length, take lines that are at least 1 km long
    lines = [l for l in lines if l.length > 1000]
    lines.sort(key=lambda x: x.length, reverse=True)
    
    if not lines:
        print("ERROR: No suitable baseline lines found")
        return
    
    # Use the longest continuous coastal line as baseline
    # Try to merge adjacent lines first
    try:
        merged = linemerge(MultiLineString(lines))
        if merged.geom_type == 'LineString':
            baseline_candidates = [merged]
        else:
            baseline_candidates = list(merged.geoms)
    except Exception:
        baseline_candidates = lines
    
    # Take the longest merged line
    baseline_candidates.sort(key=lambda x: x.length, reverse=True)
    raw_baseline = baseline_candidates[0]
    
    # Smooth with moderate tolerance (100m) — suppress pixel noise but keep coastal shape
    baseline = smooth_line(raw_baseline, tolerance=100)
    
    print(f"Raw baseline length: {raw_baseline.length:.0f} m")
    print(f"Smoothed baseline length: {baseline.length:.0f} m")
    print(f"Smoothed vertex count: {len(baseline.coords)}")
    
    # Generate transects at 100m spacing, 2km length
    ids, transects = create_transects(baseline, spacing=100, length=2000)
    
    gdf = gpd.GeoDataFrame(
        {"transect_id": ids},
        geometry=transects,
        crs="EPSG:32647",
    )
    
    out_path = Path("data/analysis/rayong/transects/rayong_transects.geojson")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_crs(epsg=4326).to_file(out_path, driver="GeoJSON")
    print(f"Created {len(transects)} transects -> {out_path}")
    
    # Also save the baseline for reference
    baseline_gdf = gpd.GeoDataFrame(
        {"id": ["baseline"]},
        geometry=[baseline],
        crs="EPSG:32647",
    )
    baseline_path = Path("data/analysis/rayong/transects/rayong_baseline.geojson")
    baseline_gdf.to_crs(epsg=4326).to_file(baseline_path, driver="GeoJSON")
    print(f"Baseline saved -> {baseline_path}")


if __name__ == "__main__":
    main()
