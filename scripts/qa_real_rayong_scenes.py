#!/usr/bin/env python3
import pandas as pd
import json

def main():
    print("Reconfirming 3 real Rayong scenes...")
    audit = pd.read_csv("data/analysis/rayong/satellite_footprint_audit.csv")
    catalog = pd.read_csv("data/catalog/rayong_sentinel2_scenes.csv")
    
    dates = ["2018-02-06", "2021-12-27", "2025-12-21"]
    
    for d in dates:
        date_compact = d.replace("-", "")
        m = audit[audit["scene_id"].str.contains(date_compact)]
        if len(m) == 0:
            print(f"FAIL: {d} missing from audit")
            return
            
        row = m.iloc[0]
        if row["classification"] != "RAYONG_CONFIRMED":
            print(f"FAIL: {d} is not RAYONG_CONFIRMED")
            return
            
        if row["crs"] != "EPSG:32647":
            print(f"FAIL: {d} has CRS {row['crs']}")
            return
            
        # check catalog
        m_cat = catalog[catalog["scene_id"] == row["scene_id"]]
        if len(m_cat) == 0:
            print(f"FAIL: {d} missing from Rayong catalog")
            return
            
    print("All 3 real Rayong scenes passed QA constraints.")
    print("Screening dataset preserved.")

if __name__ == "__main__":
    main()
