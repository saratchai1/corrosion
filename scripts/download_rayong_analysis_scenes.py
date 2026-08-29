#!/usr/bin/env python3
import pandas as pd
import subprocess
import argparse
from pathlib import Path
import sys
import json

def assert_raster_intersects_aoi(raster_path, aoi_path="data/aoi/rayong_coastal_analysis_aoi.geojson"):
    import rasterio
    from rasterio.warp import transform_bounds
    import geopandas as gpd
    from shapely.geometry import box
    
    rayong_aoi = gpd.read_file(aoi_path).to_crs("EPSG:4326").geometry.unary_union
    
    with rasterio.open(raster_path) as src:
        crs = src.crs
        if crs.to_string() != "EPSG:4326":
            minx, miny, maxx, maxy = transform_bounds(crs, "EPSG:4326", *src.bounds)
        else:
            minx, miny, maxx, maxy = src.bounds
            
    geom = box(minx, miny, maxx, maxy)
    r_frac = geom.intersection(rayong_aoi).area / rayong_aoi.area
    
    if r_frac < 0.1:
        raise ValueError(f"Raster footprint {raster_path} fails geographic safety check (intersection {r_frac:.2f})")
    
    print(f"Safety check passed for {raster_path} (intersection fraction: {r_frac:.2f})")
    return True

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dates", nargs="+", help="YYYY-MM-DD dates to download")
    args = parser.parse_args()
    
    if not args.dates:
        print("Provide --dates YYYY-MM-DD")
        return
        
    for date_str in args.dates:
        print(f"\n--- Downloading Rayong Scene for {date_str} ---")
        cmd = [
            "python", "scripts/download_satellite_data_rayong.py", "sentinel2",
            "--start", date_str,
            "--end", date_str,
            "--download"
        ]
        
        res = subprocess.run(cmd)
        if res.returncode != 0:
            print(f"Download failed for {date_str}")
            continue
            
        # Audit it
        print("Running safety check footprint audit...")
        subprocess.run(["python", "scripts/audit_rayong_satellite_footprints.py"])
        
        # Verify classification
        audit_df = pd.read_csv("data/analysis/rayong/satellite_footprint_audit.csv")
        date_compact = date_str.replace("-", "")
        matching = audit_df[audit_df["scene_id"].str.contains(date_compact)]
        
        if len(matching) == 0:
            print(f"ERROR: Could not find downloaded scene for {date_str} in audit")
            sys.exit(1)
            
        latest = matching.iloc[-1]
        if latest["classification"] != "RAYONG_CONFIRMED":
            print(f"ERROR: Scene {latest['scene_id']} classified as {latest['classification']}. FAILED geographic safety check.")
            sys.exit(1)
            
        print(f"SUCCESS: {latest['scene_id']} is RAYONG_CONFIRMED.")

if __name__ == "__main__":
    main()
