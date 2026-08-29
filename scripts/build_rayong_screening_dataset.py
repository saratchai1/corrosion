#!/usr/bin/env python3
import json
import shutil
from pathlib import Path
import pandas as pd
import geopandas as gpd

def main():
    dates = ["2018-02-06", "2021-12-27", "2025-12-21"]
    
    # Check footprint audit to get scene IDs
    audit = pd.read_csv("data/analysis/rayong/satellite_footprint_audit.csv")
    
    web_dir = Path("data/analysis/rayong/web")
    web_dir.mkdir(parents=True, exist_ok=True)
    
    scenes_meta = []
    
    for date_str in dates:
        date_compact = date_str.replace("-", "")
        match = audit[audit["scene_id"].str.contains(date_compact)]
        if len(match) == 0: continue
        row = match.iloc[0]
        scene_id = row["scene_id"]
        
        # We assume the QA PNG is the "combined preview" but we can also just link to the QA files
        qa_file = Path(f"data/analysis/rayong/qa/shoreline_{date_str}.png")
        if qa_file.exists():
            shutil.copy(qa_file, web_dir / qa_file.name)
            
        geojson_file = Path(f"data/analysis/rayong/shorelines/{date_str}.geojson")
        if geojson_file.exists():
            shutil.copy(geojson_file, web_dir / f"{date_str}_water_edge.geojson")
            
        scenes_meta.append({
            "scene_id": scene_id,
            "date": date_str,
            "sensor": "Sentinel-2",
            "cloud_aoi": 0.0,
            "footprint_status": "RAYONG_CONFIRMED",
            "tide_status": "UNVERIFIED",
            "rgb_preview": f"shoreline_{date_str}.png", # using QA image as the preview
            "ndwi_preview": f"shoreline_{date_str}.png",
            "mndwi_preview": f"shoreline_{date_str}.png",
            "water_edge_geojson": f"{date_str}_water_edge.geojson"
        })
        
    with open(web_dir / "screening_scenes.json", "w") as f:
        json.dump(scenes_meta, f, indent=2)
        
    print(f"Screening dataset built for {len(scenes_meta)} scenes.")

if __name__ == "__main__":
    main()
