import pandas as pd
import geopandas as gpd
from pathlib import Path
import numpy as np

def main():
    transects = gpd.read_file("data/analysis/rayong/transects/rayong_transects.geojson")
    
    records = []
    for _, row in transects.iterrows():
        records.append({
            "transect_id": row["transect_id"],
            "n_observations": 1,
            "earliest_date": "2025-02-09",
            "latest_date": "2025-02-09",
            "earliest_tide_m": "unverified",
            "latest_tide_m": "unverified",
            "tide_range_m": "unverified",
            "NSM_m": "NA",
            "EPR_m_per_year": "NA",
            "quality_flag": "insufficient_observations"
        })
        
    df = pd.DataFrame(records)
    out_dir = Path("data/analysis/rayong/change_metrics")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "shoreline_change_by_transect.csv"
    
    df.to_csv(out_path, index=False)
    print(f"Change metrics saved to {out_path} (Using NA / insufficient_observations)")

if __name__ == "__main__":
    main()
