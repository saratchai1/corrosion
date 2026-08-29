#!/usr/bin/env python3
"""Compare tide predictions between RTN stations to assess phase consistency."""
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path

def load_station(station_id: str, datum: str = "msl") -> pd.DataFrame:
    path = f"data/tide/rayong/processed/{station_id}_2026_{datum}.csv"
    df = pd.read_csv(path)
    df['dt_utc'] = pd.to_datetime(df['datetime_utc'])
    df['dt_bkk'] = pd.to_datetime(df['datetime_bangkok'])
    return df

def main():
    pr = load_station("pak_nam_rayong")
    mt = load_station("map_ta_phut")
    ls = load_station("laem_sing")
    
    # Merge on UTC time
    merged = pr[['dt_utc', 'height_m']].rename(columns={'height_m': 'PR_m'})
    merged = merged.merge(mt[['dt_utc', 'height_m']].rename(columns={'height_m': 'MT_m'}), on='dt_utc')
    merged = merged.merge(ls[['dt_utc', 'height_m']].rename(columns={'height_m': 'LS_m'}), on='dt_utc')
    
    # Correlations
    print("=== Station Comparison (2026 MSL) ===")
    print(f"Records: {len(merged)}")
    print(f"\nCorrelation matrix:")
    corr = merged[['PR_m', 'MT_m', 'LS_m']].corr()
    print(corr.to_string())
    
    # Phase lag analysis: find optimal lag for each pair
    print(f"\nPR range: {pr['height_m'].min():.2f} to {pr['height_m'].max():.2f} m")
    print(f"MT range: {mt['height_m'].min():.2f} to {mt['height_m'].max():.2f} m")
    print(f"LS range: {ls['height_m'].min():.2f} to {ls['height_m'].max():.2f} m")
    
    pr_arr = merged['PR_m'].values
    mt_arr = merged['MT_m'].values
    ls_arr = merged['LS_m'].values
    
    # Cross-correlation for phase lag
    max_lag = 6  # hours
    for name_a, arr_a, name_b, arr_b in [
        ("PR", pr_arr, "MT", mt_arr),
        ("PR", pr_arr, "LS", ls_arr),
        ("MT", mt_arr, "LS", ls_arr),
    ]:
        best_corr = -1
        best_lag = 0
        for lag in range(-max_lag, max_lag + 1):
            if lag >= 0:
                c = np.corrcoef(arr_a[lag:], arr_b[:len(arr_b)-lag])[0, 1]
            else:
                c = np.corrcoef(arr_a[:len(arr_a)+lag], arr_b[-lag:])[0, 1]
            if c > best_corr:
                best_corr = c
                best_lag = lag
        print(f"\n{name_a} vs {name_b}: best_lag={best_lag}h, corr@lag={best_corr:.4f}, corr@0={np.corrcoef(arr_a, arr_b)[0,1]:.4f}")
    
    # Difference stats
    merged['PR_MT_diff'] = merged['PR_m'] - merged['MT_m']
    merged['PR_LS_diff'] = merged['PR_m'] - merged['LS_m']
    
    print(f"\nPR - MT difference: mean={merged['PR_MT_diff'].mean():.3f} m, std={merged['PR_MT_diff'].std():.3f} m")
    print(f"PR - LS difference: mean={merged['PR_LS_diff'].mean():.3f} m, std={merged['PR_LS_diff'].std():.3f} m")
    
    # Save comparison CSV
    out_csv = Path("data/analysis/rayong/tide_station_comparison.csv")
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    comparison_df = pd.DataFrame({
        "pair": ["PR-MT", "PR-LS", "MT-LS"],
        "corr_at_zero_lag": [
            np.corrcoef(pr_arr, mt_arr)[0,1],
            np.corrcoef(pr_arr, ls_arr)[0,1],
            np.corrcoef(mt_arr, ls_arr)[0,1],
        ],
        "mean_diff_m": [
            merged['PR_MT_diff'].mean(),
            merged['PR_LS_diff'].mean(),
            (merged['MT_m'] - merged['LS_m']).mean(),
        ],
        "std_diff_m": [
            merged['PR_MT_diff'].std(),
            merged['PR_LS_diff'].std(),
            (merged['MT_m'] - merged['LS_m']).std(),
        ],
    })
    comparison_df.to_csv(out_csv, index=False)
    
    # Plot: 7 days in Jan (spring tide) and 7 days around Jan 20 (neap)
    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=False)
    
    spring = merged[(merged['dt_utc'] >= '2026-01-01') & (merged['dt_utc'] < '2026-01-08')]
    neap = merged[(merged['dt_utc'] >= '2026-01-18') & (merged['dt_utc'] < '2026-01-25')]
    
    for ax, subset, title in [(axes[0], spring, "Spring Tide (Jan 1-7, 2026)"),
                                (axes[1], neap, "Neap Tide (Jan 18-24, 2026)")]:
        ax.plot(subset['dt_utc'], subset['PR_m'], label='Pak Nam Rayong', linewidth=1.5)
        ax.plot(subset['dt_utc'], subset['MT_m'], label='Map Ta Phut', linewidth=1.5)
        ax.plot(subset['dt_utc'], subset['LS_m'], label='Laem Sing', linewidth=1.5)
        ax.set_title(title)
        ax.set_ylabel('Water Level (m, MSL)')
        ax.legend()
        ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    out_png = Path("data/analysis/rayong/qa/tide_station_comparison.png")
    plt.savefig(out_png, dpi=200)
    print(f"\nSaved comparison figure to {out_png}")

if __name__ == "__main__":
    main()
