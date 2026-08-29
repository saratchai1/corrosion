import pandas as pd
import geopandas as gpd
from pathlib import Path

def main():
    transects = gpd.read_file("data/analysis/rayong/transects/rayong_transects.geojson")
    
    # Since we only have a single shoreline extracted for the prototype, 
    # we cannot compute a real NSM/EPR. We'll populate the structure with the single observation.
    
    records = []
    for _, row in transects.iterrows():
        records.append({
            "transect_id": row["transect_id"],
            "earliest_date": "2025-02-09",
            "latest_date": "2025-02-09",
            "earliest_tide": "unverified",
            "latest_tide": "unverified",
            "n_observations": 1,
            "NSM_m": 0.0,
            "EPR_m_per_year": 0.0,
            "quality_flag": "INSUFFICIENT_DATA"
        })
        
    df = pd.DataFrame(records)
    out_dir = Path("data/analysis/rayong/change_metrics")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "shoreline_change_by_transect.csv"
    
    df.to_csv(out_path, index=False)
    print(f"Change metrics initialized and saved to {out_path}")

if __name__ == "__main__":
    main()
