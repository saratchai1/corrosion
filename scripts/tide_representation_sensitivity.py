#!/usr/bin/env python3
"""Evaluate sensitivity of tide representation (PR only vs LS only vs PR+LS bracketing)."""

import pandas as pd
import json
import numpy as np
from pathlib import Path
from scipy.interpolate import interp1d

def load_tide(station_id, datum="msl"):
    path = Path(f"data/tide/rayong/processed/{station_id}_2026_{datum}.csv")
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    df['dt_utc'] = pd.to_datetime(df['datetime_utc'])
    return df.set_index('dt_utc').sort_index()

def main():
    pr = load_tide("pak_nam_rayong")
    ls = load_tide("laem_sing")
    mt = load_tide("map_ta_phut")
    
    if pr.empty or ls.empty or mt.empty:
        print("Missing station data. Ensure 2026 data is parsed.")
        return

    # Interpolate to 5-minute intervals
    # Create common 5-min index for the entire 2026 year
    start = pr.index.min()
    end = pr.index.max()
    freq_5min = pd.date_range(start=start, end=end, freq='5min')
    
    # Use scipy interp1d for fast interpolation
    def interpolate_5m(df):
        f = interp1d(df.index.astype(np.int64), df['height_m'], kind='linear', fill_value='extrapolate')
        return f(freq_5min.astype(np.int64))

    pr_5m = interpolate_5m(pr)
    ls_5m = interpolate_5m(ls)
    mt_5m = interpolate_5m(mt)
    
    df_5m = pd.DataFrame({
        'dt_utc': freq_5min,
        'PR_m': pr_5m,
        'LS_m': ls_5m,
        'MT_m': mt_5m
    }).set_index('dt_utc')
    
    # 1. Cross correlation allowing sub-hour lag
    # We will check lags up to +/- 3 hours (36 * 5 mins)
    max_lag_steps = 36
    results = []
    
    for pair_name, s1, s2 in [("PR_vs_LS", 'PR_m', 'LS_m'), ("PR_vs_MT", 'PR_m', 'MT_m')]:
        best_corr = -1
        best_lag = 0
        arr1 = df_5m[s1].values
        arr2 = df_5m[s2].values
        
        for lag in range(-max_lag_steps, max_lag_steps + 1):
            if lag >= 0:
                c = np.corrcoef(arr1[lag:], arr2[:len(arr2)-lag])[0, 1]
            else:
                c = np.corrcoef(arr1[:len(arr1)+lag], arr2[-lag:])[0, 1]
                
            if c > best_corr:
                best_corr = c
                best_lag = lag
                
        lag_minutes = best_lag * 5
        mean_offset = np.mean(arr1 - arr2)
        rmse = np.sqrt(np.mean((arr1 - arr2)**2))
        amp_ratio = (np.max(arr1) - np.min(arr1)) / (np.max(arr2) - np.min(arr2))
        
        results.append({
            "pair": pair_name,
            "optimal_lag_minutes": lag_minutes,
            "max_correlation": best_corr,
            "mean_offset_m": mean_offset,
            "rmse_m": rmse,
            "amplitude_ratio": amp_ratio
        })

    # 2. Evaluate tide representations at satellite acquisition times
    # We'll simulate satellite acquisition times at 10:30 AM local time (03:30 UTC) every 5 days
    sat_times = pd.date_range(start='2026-01-01 03:30:00', end='2026-12-31 03:30:00', freq='5D')
    sat_times = sat_times.tz_localize('UTC')
    
    # Distances to AOI centroid (from earlier script)
    dist_PR = 48.6
    dist_LS = 45.8
    # Weights are inverse distance
    w_PR = 1.0 / dist_PR
    w_LS = 1.0 / dist_LS
    
    df_sat = df_5m.reindex(sat_times, method='nearest')
    
    # Option A: PR only
    # Option B: LS only
    # Option C: Weighted PR + LS
    df_sat['opt_A'] = df_sat['PR_m']
    df_sat['opt_B'] = df_sat['LS_m']
    df_sat['opt_C'] = (w_PR * df_sat['PR_m'] + w_LS * df_sat['LS_m']) / (w_PR + w_LS)
    
    # Test pass/fail thresholds against a target of 0.0m MSL, window 0.20m
    target_tide = 0.0
    window = 0.20
    
    def pass_fail(val):
        return 'PASS' if abs(val - target_tide) <= window else 'FAIL'
        
    df_sat['status_A'] = df_sat['opt_A'].apply(pass_fail)
    df_sat['status_B'] = df_sat['opt_B'].apply(pass_fail)
    df_sat['status_C'] = df_sat['opt_C'].apply(pass_fail)
    
    # How many changed?
    a_vs_c_changed = (df_sat['status_A'] != df_sat['status_C']).sum()
    b_vs_c_changed = (df_sat['status_B'] != df_sat['status_C']).sum()
    
    # Save results
    out_dir = Path("data/analysis/rayong")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Write summary of lags to json
    out_json = out_dir / "tide_lag_summary.json"
    with open(out_json, "w") as f:
        json.dump({
            "lag_analysis": results,
            "scene_selection_sensitivity": {
                "total_simulated_scenes": len(df_sat),
                "PR_only_vs_Bracketing_changes": int(a_vs_c_changed),
                "LS_only_vs_Bracketing_changes": int(b_vs_c_changed)
            }
        }, f, indent=2)
        
    # Write full sensitivity CSV
    out_csv = out_dir / "tide_representation_sensitivity.csv"
    df_sat.to_csv(out_csv)
    
    print(f"Sub-hour lag PR vs LS: {results[0]['optimal_lag_minutes']} minutes (r={results[0]['max_correlation']:.4f})")
    print(f"Sub-hour lag PR vs MT: {results[1]['optimal_lag_minutes']} minutes (r={results[1]['max_correlation']:.4f})")
    print(f"Selection changes (PR vs Bracketing): {a_vs_c_changed} / {len(df_sat)}")
    print(f"Results saved to {out_csv.name}")

if __name__ == "__main__":
    main()
