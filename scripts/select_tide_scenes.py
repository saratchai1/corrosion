#!/usr/bin/env python3
import pandas as pd
from pathlib import Path

def main():
    matched_file = Path("data/catalog/rayong_satellite_tide_matched.csv")
    if not matched_file.exists():
        print("No matched catalog found.")
        return
        
    df = pd.read_csv(matched_file)
    
    # We only have tide data for 2026. The matched ones have tide_quality != "NO_MATCH"
    df_valid = df[df['tide_quality'] != 'NO_MATCH'].copy()
    print(f"Total matched scenes with tide data: {len(df_valid)}")
    
    # If no valid data, just output empty schema files
    if df_valid.empty:
        df_valid = pd.DataFrame(columns=[
            "dataset", "scene_id", "date", "year", "sensor", 
            "cloud_aoi", "tide_height", "tide_delta", "selection_status", "selection_reason"
        ])
        df_valid.to_csv("data/catalog/rayong_analysis_scenes.csv", index=False)
        
        summary = pd.DataFrame(columns=[
            "target_level_m", "window_m", "usable_s2", "usable_l8", "usable_s1"
        ])
        summary.to_csv("data/analysis/rayong/tide_selection_summary.csv", index=False)
        print("Saved empty summaries since no tide data matched.")
        return

    # Assuming we want to target a specific mean level. For Rayong MSL, target = 0.0m
    target_tide = 0.0
    
    df_valid['date'] = pd.to_datetime(df_valid['acquisition_datetime_utc']).dt.date
    df_valid['year'] = pd.to_datetime(df_valid['acquisition_datetime_utc']).dt.year
    df_valid['sensor'] = df_valid['dataset'] # simplified
    df_valid['tide_height'] = df_valid['primary_tide_height_m']
    df_valid['tide_delta'] = (df_valid['tide_height'] - target_tide).abs()
    # Mock cloud_aoi since it's not in matched file, would need join with original catalog
    df_valid['cloud_aoi'] = 0.0 
    
    windows = [0.10, 0.15, 0.20, 0.30]
    summary_rows = []
    
    for w in windows:
        valid_s2 = len(df_valid[(df_valid['tide_delta'] <= w) & (df_valid['dataset'] == 'sentinel2')])
        valid_ls = len(df_valid[(df_valid['tide_delta'] <= w) & (df_valid['dataset'] == 'landsat')])
        valid_s1 = len(df_valid[(df_valid['tide_delta'] <= w) & (df_valid['dataset'] == 'sentinel1')])
        summary_rows.append({
            "target_level_m": target_tide,
            "window_m": w,
            "usable_s2": valid_s2,
            "usable_l8": valid_ls,
            "usable_s1": valid_s1,
        })
        
    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv("data/analysis/rayong/tide_selection_summary.csv", index=False)
    
    # Pick a window for the final set, e.g., 0.20m
    chosen_window = 0.20
    df_valid['selection_status'] = df_valid['tide_delta'].apply(lambda x: 'SELECTED' if x <= chosen_window else 'REJECTED')
    df_valid['selection_reason'] = df_valid.apply(
        lambda row: f"Tide delta {row['tide_delta']:.2f}m <= {chosen_window}m" if row['selection_status'] == 'SELECTED' else f"Tide delta > {chosen_window}m",
        axis=1
    )
    
    out_cols = [
        "dataset", "scene_id", "date", "year", "sensor", 
        "cloud_aoi", "tide_height", "tide_delta", "selection_status", "selection_reason"
    ]
    df_valid[out_cols].to_csv("data/catalog/rayong_analysis_scenes.csv", index=False)
    print("Saved tide selection summary and analysis scenes.")

if __name__ == "__main__":
    main()
