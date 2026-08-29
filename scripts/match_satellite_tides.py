#!/usr/bin/env python3
"""Match satellite acquisition times to RTN tide predictions via linear interpolation."""
import csv
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

BKK = ZoneInfo("Asia/Bangkok")

def load_tide(station_id: str, datum: str = "msl") -> pd.DataFrame:
    """Load processed tide CSV. Returns DataFrame with dt_utc index and height_m column."""
    path = Path(f"data/tide/rayong/processed/{station_id}_2026_{datum}.csv")
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    df['dt_utc'] = pd.to_datetime(df['datetime_utc'])
    df = df.set_index('dt_utc').sort_index()
    return df

def interpolate_tide(tide_df: pd.DataFrame, acq_time: pd.Timestamp) -> dict:
    """Interpolate tide height at acquisition time between hourly records."""
    if tide_df.empty:
        return {"height_m": None, "quality": "NO_MATCH", "before": None, "after": None, "frac": None}
    
    # Ensure tz-aware comparison
    if acq_time.tzinfo is None:
        acq_time = acq_time.tz_localize('UTC')
    elif str(acq_time.tzinfo) != 'UTC':
        acq_time = acq_time.tz_convert('UTC')
    
    # Find bounding hourly records
    before_mask = tide_df.index <= acq_time
    after_mask = tide_df.index >= acq_time
    
    if not before_mask.any() or not after_mask.any():
        return {"height_m": None, "quality": "NO_MATCH", "before": None, "after": None, "frac": None}
    
    t_before = tide_df.index[before_mask][-1]
    t_after = tide_df.index[after_mask][0]
    
    h_before = tide_df.loc[t_before, 'height_m']
    h_after = tide_df.loc[t_after, 'height_m']
    
    if t_before == t_after:
        return {
            "height_m": float(h_before),
            "quality": "OFFICIAL_PREDICTION_EXACT",
            "before": str(t_before),
            "after": str(t_after),
            "frac": 0.0,
        }
    
    # Linear interpolation
    total_seconds = (t_after - t_before).total_seconds()
    elapsed = (acq_time - t_before).total_seconds()
    frac = elapsed / total_seconds if total_seconds > 0 else 0
    
    height = float(h_before) + frac * (float(h_after) - float(h_before))
    
    return {
        "height_m": round(height, 3),
        "quality": "OFFICIAL_PREDICTION_INTERPOLATED",
        "before": str(t_before),
        "after": str(t_after),
        "frac": round(frac, 4),
    }


def main():
    # Load tide data for all stations
    stations = ["pak_nam_rayong", "map_ta_phut", "laem_sing"]
    tide_data = {}
    for sid in stations:
        df = load_tide(sid, "msl")
        if not df.empty:
            tide_data[sid] = df
            print(f"Loaded {len(df)} tide records for {sid}")
        else:
            print(f"WARNING: No tide data for {sid}")
    
    # Load satellite catalogs
    catalogs = {
        "sentinel2": "data/catalog/rayong_sentinel2_scenes.csv",
        "landsat": "data/catalog/rayong_landsat_scenes.csv",
        "sentinel1": "data/catalog/rayong_sentinel1_scenes.csv",
    }
    
    results = []
    matched = 0
    unmatched = 0
    
    for dataset, path in catalogs.items():
        if not Path(path).exists():
            print(f"Catalog not found: {path}")
            continue
        
        df = pd.read_csv(path)
        print(f"\n{dataset}: {len(df)} scenes")
        
        for _, row in df.iterrows():
            acq_utc = pd.Timestamp(row['acquisition_datetime_utc'])
            acq_bkk = acq_utc.tz_convert(BKK) if acq_utc.tzinfo else pd.Timestamp(row['acquisition_datetime_bangkok'])
            
            # Interpolate for each station
            pr = interpolate_tide(tide_data.get("pak_nam_rayong", pd.DataFrame()), acq_utc)
            mt = interpolate_tide(tide_data.get("map_ta_phut", pd.DataFrame()), acq_utc)
            ls = interpolate_tide(tide_data.get("laem_sing", pd.DataFrame()), acq_utc)
            
            # Primary = Pak Nam Rayong (closest relevant station)
            primary = pr
            
            result = {
                "dataset": dataset,
                "scene_id": row.get("scene_id", ""),
                "acquisition_datetime_utc": str(acq_utc),
                "acquisition_datetime_bangkok": str(acq_bkk),
                "pak_nam_rayong_height_m": pr["height_m"],
                "map_ta_phut_height_m": mt["height_m"],
                "laem_sing_height_m": ls["height_m"],
                "tide_datum": "MSL",
                "primary_tide_height_m": primary["height_m"],
                "primary_tide_method": primary["quality"],
                "nearest_tide_time_before": primary["before"],
                "nearest_tide_time_after": primary["after"],
                "interpolation_fraction": primary["frac"],
                "tide_quality": primary["quality"],
                "tide_source_type": "PREDICTED",
            }
            results.append(result)
            
            if primary["height_m"] is not None:
                matched += 1
            else:
                unmatched += 1
    
    # Write output
    out_path = Path("data/catalog/rayong_satellite_tide_matched.csv")
    if results:
        out_df = pd.DataFrame(results)
        out_df.to_csv(out_path, index=False)
        print(f"\n=== Results ===")
        print(f"Total scenes: {len(results)}")
        print(f"Matched: {matched}")
        print(f"Unmatched: {unmatched}")
        print(f"Saved to {out_path}")
    else:
        print("No results to write")


if __name__ == "__main__":
    main()
