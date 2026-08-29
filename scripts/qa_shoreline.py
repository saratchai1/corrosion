import rasterio
from rasterio.plot import show
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

def normalize(array):
    array_min, array_max = np.percentile(array, (2, 98))
    return np.clip((array - array_min) / (array_max - array_min), 0, 1)

def main():
    scene_dir = Path("data/satellite/sentinel2/2025/S2B_47PQQ_20250209_0_L2A")
    date_str = "2025-02-09"
    
    # Read RGB
    red = rasterio.open(scene_dir / "B4_10m.tif")
    green = rasterio.open(scene_dir / "B3_10m.tif")
    blue = rasterio.open(scene_dir / "B2_10m.tif")
    
    r = normalize(red.read(1))
    g = normalize(green.read(1))
    b = normalize(blue.read(1))
    rgb = np.dstack((r, g, b))
    
    # Read Vectors
    shoreline = gpd.read_file(f"data/analysis/rayong/shorelines/{date_str}.geojson")
    plots = gpd.read_file("data/aoi/rayong_planting_plots_validated.geojson")
    aoi = gpd.read_file("data/aoi/rayong_coastal_analysis_aoi.geojson")
    
    shoreline_proj = shoreline.to_crs(red.crs)
    plots_proj = plots.to_crs(red.crs)
    aoi_proj = aoi.to_crs(red.crs)
    
    fig, ax = plt.subplots(figsize=(12, 10))
    
    from rasterio.plot import show
    show(np.moveaxis(rgb, 2, 0), ax=ax, transform=red.transform)
    
    aoi_proj.plot(ax=ax, facecolor="none", edgecolor="yellow", linestyle="--", linewidth=2, label="AOI")
    plots_proj.plot(ax=ax, facecolor="none", edgecolor="cyan", linewidth=2, label="Planting Plots")
    shoreline_proj.plot(ax=ax, color="red", linewidth=1.5, label="Extracted Shoreline")
    
    ax.set_title(f"Shoreline QA - {date_str} (Sentinel-2 NDWI)\nTide: Unverified")
    
    from matplotlib.lines import Line2D
    custom_lines = [
        Line2D([0], [0], color="yellow", lw=2, linestyle="--", label="Analysis AOI"),
        Line2D([0], [0], color="cyan", lw=2, label="Planting Plots"),
        Line2D([0], [0], color="red", lw=1.5, label="Extracted Shoreline")
    ]
    ax.legend(handles=custom_lines, loc="upper right")
    
    out_dir = Path("data/analysis/rayong/qa")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"shoreline_{date_str}.png"
    plt.savefig(out_path, dpi=300)
    print(f"Saved QA overlay to {out_path}")

if __name__ == "__main__":
    main()
