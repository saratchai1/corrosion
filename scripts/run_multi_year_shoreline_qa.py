#!/usr/bin/env python3
import rasterio
from rasterio.plot import show
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
import subprocess

def normalize(array):
    # Avoid nan/inf issues
    valid = array[np.isfinite(array)]
    if len(valid) == 0:
        return array
    array_min, array_max = np.percentile(valid, (2, 98))
    return np.clip((array - array_min) / (max(array_max - array_min, 0.001)), 0, 1)

def run_qa(scene_dir: Path):
    scene_id = scene_dir.name
    date_str = scene_id.split("_")[2][:8]
    date_formatted = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    
    print(f"\nProcessing {date_formatted} ({scene_id})")
    
    # Run the extraction script
    subprocess.run([
        "python", "scripts/extract_rayong_shoreline.py",
        "--scene-dir", str(scene_dir),
        "--date", date_formatted
    ])
    
    # Read RGB
    red_path = scene_dir / "B4_10m.tif"
    green_path = scene_dir / "B3_10m.tif"
    blue_path = scene_dir / "B2_10m.tif"
    
    if not red_path.exists():
        print(f"Skipping {date_formatted} - RGB not found")
        return
        
    red = rasterio.open(red_path)
    green = rasterio.open(green_path)
    blue = rasterio.open(blue_path)
    
    r = normalize(red.read(1))
    g = normalize(green.read(1))
    b = normalize(blue.read(1))
    rgb = np.dstack((r, g, b))
    
    shoreline_path = f"data/analysis/rayong/shorelines/{date_formatted}.geojson"
    if not Path(shoreline_path).exists():
        print(f"Skipping {date_formatted} - Shoreline geojson not found")
        return
        
    shoreline = gpd.read_file(shoreline_path)
    plots = gpd.read_file("data/aoi/rayong_planting_plots_validated.geojson")
    aoi = gpd.read_file("data/aoi/rayong_coastal_analysis_aoi.geojson")
    
    shoreline_proj = shoreline.to_crs(red.crs)
    plots_proj = plots.to_crs(red.crs)
    aoi_proj = aoi.to_crs(red.crs)
    
    fig, ax = plt.subplots(figsize=(12, 10))
    
    show(np.moveaxis(rgb, 2, 0), ax=ax, transform=red.transform)
    
    aoi_proj.plot(ax=ax, facecolor="none", edgecolor="yellow", linestyle="--", linewidth=2)
    plots_proj.plot(ax=ax, facecolor="none", edgecolor="cyan", linewidth=2)
    
    if not shoreline_proj.empty:
        shoreline_proj.plot(ax=ax, color="red", linewidth=1.5)
    
    ax.set_title(f"Shoreline QA - {date_formatted} (Sentinel-2 NDWI Otsu)")
    
    from matplotlib.lines import Line2D
    custom_lines = [
        Line2D([0], [0], color="yellow", lw=2, linestyle="--", label="Analysis AOI"),
        Line2D([0], [0], color="cyan", lw=2, label="Planting Plots"),
        Line2D([0], [0], color="red", lw=1.5, label="Extracted Shoreline")
    ]
    ax.legend(handles=custom_lines, loc="upper right")
    
    out_dir = Path("data/analysis/rayong/qa")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"shoreline_{date_formatted}.png"
    plt.savefig(out_path, dpi=300)
    plt.close()
    print(f"Saved QA overlay to {out_path}")

def main():
    base_dir = Path("data/satellite/sentinel2")
    if not base_dir.exists():
        return
        
    for year_dir in base_dir.iterdir():
        if year_dir.is_dir():
            for scene_dir in year_dir.iterdir():
                if scene_dir.is_dir() and "L2A" in scene_dir.name:
                    run_qa(scene_dir)

if __name__ == "__main__":
    main()
