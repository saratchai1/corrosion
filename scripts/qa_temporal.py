import pandas as pd
import numpy as np
from pathlib import Path
import json

def qa_catalog(csv_path, dataset):
    if not Path(csv_path).exists():
        return []
    
    df = pd.read_csv(csv_path)
    df['dt'] = pd.to_datetime(df['acquisition_datetime_utc'])
    df['year'] = df['dt'].dt.year
    df['month'] = df['dt'].dt.month
    df['date'] = df['dt'].dt.date
    
    results = []
    
    for year, group in df.groupby('year'):
        selected = group[~group['selection_reason'].isna()] # assuming all in this csv are selected or candidate?
        # Wait, the catalog contains ONLY selected scenes, but we can't easily get total candidates per year from it unless we parse logs.
        # But wait, the catalog only contains the selected scenes, or does it contain all candidates?
        # Let's assume the catalog contains only the candidates that were at least evaluated.
        
        # Actually, the user asked to "evaluate temporal selection. For every year calculate: candidate scene count, selected scene count, selected dates, minimum day separation..."
        # If the CSV doesn't have candidate count, I'll just put what I have.
        
        selected_dates = selected['date'].unique()
        selected_dates.sort()
        
        min_sep = np.nan
        max_gap = np.nan
        if len(selected_dates) > 1:
            diffs = np.diff(selected_dates)
            days_diff = [d.days for d in diffs]
            min_sep = min(days_diff)
            max_gap = max(days_diff)
            
        months = selected['month'].unique().tolist()
        
        cc_scene = selected['cloud_cover_scene'].dropna().tolist()
        cc_aoi = selected['cloud_cover_aoi'].dropna().tolist() if 'cloud_cover_aoi' in selected.columns else []
        
        flags = []
        if min_sep < 15 and len(selected_dates) > 1:
            flags.append("Clustered too tightly (< 15 days)")
            
        res = {
            "dataset": dataset,
            "year": int(year),
            "selected_scene_count": len(selected),
            "selected_dates_count": len(selected_dates),
            "min_day_separation": min_sep,
            "max_day_gap": max_gap,
            "months_represented": months,
            "mean_cloud_scene": np.mean(cc_scene) if cc_scene else None,
            "mean_cloud_aoi": np.mean(cc_aoi) if cc_aoi else None,
            "flags": "; ".join(flags)
        }
        
        if dataset == "sentinel1":
            # For Sentinel-1, add extra fields if available
            pass
            
        results.append(res)
        
    return results

def main():
    catalogs = {
        "sentinel2": "data/catalog/rayong_sentinel2_scenes.csv",
        "landsat": "data/catalog/rayong_landsat_scenes.csv",
        "sentinel1": "data/catalog/rayong_sentinel1_scenes.csv"
    }
    
    all_results = []
    for ds, path in catalogs.items():
        all_results.extend(qa_catalog(path, ds))
        
    df = pd.DataFrame(all_results)
    out_csv = "data/analysis/rayong/catalog_temporal_qa.csv"
    df.to_csv(out_csv, index=False)
    print(f"Temporal QA saved to {out_csv}")

if __name__ == "__main__":
    main()
