#!/usr/bin/env python3
import geopandas as gpd
import pandas as pd
import json

def get_intersection_points(transects, shoreline):
    intersections = []
    
    # ensure single multi-linestring for shoreline
    if hasattr(shoreline.geometry, 'union_all'):
        sl_geom = shoreline.geometry.union_all()
    else:
        sl_geom = shoreline.geometry.unary_union
        
    for idx, row in transects.iterrows():
        t_geom = row.geometry
        pt = t_geom.intersection(sl_geom)
        
        # if multiple points, take the one closest to start of transect (offshore usually if transect is drawn landward)
        if pt.is_empty:
            intersections.append(None)
        elif pt.geom_type == 'Point':
            intersections.append(pt)
        elif pt.geom_type == 'MultiPoint':
            # closest to t_geom start
            start = t_geom.coords[0]
            pts = list(pt.geoms)
            pts.sort(key=lambda p: ((p.x - start[0])**2 + (p.y - start[1])**2))
            intersections.append(pts[0])
        else:
            intersections.append(None)
            
    return intersections

def main():
    transects = gpd.read_file("data/analysis/rayong/transects/rayong_transects_50m.geojson")
    
    dates = ["2018-02-06", "2021-12-27", "2025-12-21"]
    shorelines = {}
    
    for d in dates:
        sl = gpd.read_file(f"data/analysis/rayong/shorelines/{d}.geojson").to_crs(transects.crs)
        shorelines[d] = sl
        
    pts = {}
    for d, sl in shorelines.items():
        pts[d] = get_intersection_points(transects, sl)
        
    pairs = [
        ("2018-02-06", "2025-12-21"),
        ("2018-02-06", "2021-12-27"),
        ("2021-12-27", "2025-12-21")
    ]
    
    results = []
    
    for before, after in pairs:
        for i, row in transects.iterrows():
            t_id = row['transect_id']
            p1 = pts[before][i]
            p2 = pts[after][i]
            
            if p1 and p2:
                # distance
                dist = p1.distance(p2)
                # sign: if p2 is further along the transect, it's landward (assuming transect drawn landward)
                # let's just project onto transect line
                t_geom = row.geometry
                d1 = t_geom.project(p1)
                d2 = t_geom.project(p2)
                displacement = d2 - d1 
            else:
                displacement = None
                
            results.append({
                "transect_id": int(t_id),
                "before_date": before,
                "after_date": after,
                "apparent_displacement_m": round(displacement, 2) if displacement is not None else None,
                "quality": "SCREENING_ONLY"
            })
            
    out_file = "data/analysis/rayong/web/apparent_change_by_transect.json"
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)
        
    print(f"Calculated changes for {len(pairs)} pairs across {len(transects)} transects.")

if __name__ == "__main__":
    main()
