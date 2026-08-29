#!/usr/bin/env python3
import rasterio
from rasterio.warp import transform_bounds
import geopandas as gpd
from shapely.geometry import box
import pandas as pd
from pathlib import Path

def get_raster_bounds_4326(raster_path):
    try:
        with rasterio.open(raster_path) as src:
            crs = src.crs
            bounds = src.bounds
            
            if crs.to_string() != "EPSG:4326":
                minx, miny, maxx, maxy = transform_bounds(crs, "EPSG:4326", *bounds)
            else:
                minx, miny, maxx, maxy = bounds
            return crs.to_string(), box(minx, miny, maxx, maxy)
    except Exception as e:
        print(f"Error reading {raster_path}: {e}")
        return None, None

def main():
    rayong_aoi_path = "data/aoi/rayong_coastal_analysis_aoi.geojson"
    samut_aoi_path = "data/aoi/samut_songkhram_aoi.geojson"
    
    rayong_aoi = gpd.read_file(rayong_aoi_path).to_crs("EPSG:4326").geometry.unary_union
    samut_aoi = gpd.read_file(samut_aoi_path).to_crs("EPSG:4326").geometry.unary_union
    
    rayong_area = rayong_aoi.area
    samut_area = samut_aoi.area
    
    results = []
    
    # Iterate through all raster folders
    base_dirs = [
        Path("data/satellite/sentinel2"),
        Path("data/satellite/landsat"),
        Path("data/satellite/sentinel1")
    ]
    
    for base_dir in base_dirs:
        if not base_dir.exists(): continue
        
        for year_dir in base_dir.iterdir():
            if not year_dir.is_dir(): continue
            
            for scene_dir in year_dir.iterdir():
                if not scene_dir.is_dir(): continue
                
                # Find any .tif to open
                tifs = list(scene_dir.glob("*.tif"))
                if not tifs: continue
                
                tif_to_check = tifs[0]
                # If there's an RGB or B4, prefer it
                for t in tifs:
                    if "B4" in t.name or "B04" in t.name or "VV" in t.name:
                        tif_to_check = t
                        break
                        
                crs_str, geom = get_raster_bounds_4326(tif_to_check)
                if not geom: continue
                
                r_intersect = geom.intersection(rayong_aoi).area
                s_intersect = geom.intersection(samut_aoi).area
                
                r_frac = r_intersect / rayong_area
                s_frac = s_intersect / samut_area
                
                # Classification
                if r_frac > 0.1 and s_frac < 0.1:
                    classification = "RAYONG_CONFIRMED"
                elif s_frac > 0.1 and r_frac < 0.1:
                    classification = "SAMUT_SONGKHRAM"
                elif r_frac < 0.01 and s_frac < 0.01:
                    classification = "OTHER"
                else:
                    classification = "AMBIGUOUS"
                    
                minx, miny, maxx, maxy = geom.bounds
                
                results.append({
                    "dataset": base_dir.name,
                    "scene_id": scene_dir.name,
                    "year": year_dir.name,
                    "raster_path": str(scene_dir),
                    "crs": crs_str,
                    "min_lon": minx,
                    "min_lat": miny,
                    "max_lon": maxx,
                    "max_lat": maxy,
                    "rayong_intersection_fraction": r_frac,
                    "samut_intersection_fraction": s_frac,
                    "classification": classification
                })
                
    df = pd.DataFrame(results)
    
    out_path = Path("data/analysis/rayong/satellite_footprint_audit.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    
    print("\n--- FOOTPRINT AUDIT SUMMARY ---")
    print(df["classification"].value_counts())
    print(f"\nAudit saved to {out_path}")

if __name__ == "__main__":
    main()
