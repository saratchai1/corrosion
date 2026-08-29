#!/usr/bin/env python3
import geopandas as gpd
from shapely.geometry import LineString, MultiLineString
from shapely.ops import linemerge
import numpy as np
from pathlib import Path

def create_transects(baseline, spacing=100, length=2000):
    transects = []
    distances = np.arange(0, baseline.length, spacing)
    for i, d in enumerate(distances):
        pt = baseline.interpolate(d)
        d_before = max(0, d - 10)
        d_after = min(baseline.length, d + 10)
        pt_before = baseline.interpolate(d_before)
        pt_after = baseline.interpolate(d_after)
        dx = pt_after.x - pt_before.x
        dy = pt_after.y - pt_before.y
        if dx == 0 and dy == 0: continue
        angle = np.arctan2(dy, dx)
        perp = angle + np.pi / 2
        half = length / 2
        x1 = pt.x - half * np.cos(perp)
        y1 = pt.y - half * np.sin(perp)
        x2 = pt.x + half * np.cos(perp)
        y2 = pt.y + half * np.sin(perp)
        transects.append(LineString([(x1, y1), (x2, y2)]))
    return transects

def main():
    shoreline_path = "data/analysis/rayong/shorelines/2025-02-09.geojson"
    sl = gpd.read_file(shoreline_path).to_crs(epsg=32647)
    geom = sl.geometry.iloc[0]
    lines = list(geom.geoms) if geom.geom_type == 'MultiLineString' else [geom]
    lines = [l for l in lines if l.length > 1000]
    
    try:
        merged = linemerge(MultiLineString(lines))
        baseline_candidates = [merged] if merged.geom_type == 'LineString' else list(merged.geoms)
    except:
        baseline_candidates = lines
        
    baseline_candidates.sort(key=lambda x: x.length, reverse=True)
    raw_baseline = baseline_candidates[0]
    
    results = []
    for tol in [20, 50, 100]:
        baseline = raw_baseline.simplify(tol, preserve_topology=True)
        transects = create_transects(baseline)
        print(f"Tolerance {tol}m: length={baseline.length:.0f}m, vertices={len(baseline.coords)}, transects={len(transects)}")
        results.append({"tolerance": tol, "length_m": baseline.length, "vertices": len(baseline.coords), "transects": len(transects)})
        
    import pandas as pd
    pd.DataFrame(results).to_csv("data/analysis/rayong/transect_sensitivity.csv", index=False)

if __name__ == "__main__":
    main()
