import geopandas as gpd
import matplotlib.pyplot as plt
from pathlib import Path

def main():
    aoi_path = "data/aoi/rayong_coastal_analysis_aoi.geojson"
    plots_path = "data/aoi/rayong_planting_plots_validated.geojson"
    out_dir = Path("data/analysis/rayong/qa")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_png = out_dir / "rayong_aoi_overview.png"

    aoi = gpd.read_file(aoi_path)
    plots = gpd.read_file(plots_path)

    # Validate stats
    bbox = aoi.total_bounds
    aoi_proj = aoi.to_crs(epsg=32647)
    area_km2 = aoi_proj.geometry.area.sum() / 1e6

    print(f"AOI bbox: {bbox}")
    print(f"AOI area: {area_km2:.2f} km²")

    # Plot
    fig, ax = plt.subplots(figsize=(10, 8))
    
    aoi.plot(ax=ax, facecolor="none", edgecolor="blue", linewidth=2, label="Analysis AOI")
    plots.plot(ax=ax, facecolor="green", edgecolor="darkgreen", alpha=0.7, label="Planting Plots")
    
    # Add custom legend
    from matplotlib.lines import Line2D
    custom_lines = [
        Line2D([0], [0], color="blue", lw=2, label="Analysis AOI"),
        Line2D([0], [0], color="green", lw=4, alpha=0.7, label="Planting Plots")
    ]
    ax.legend(handles=custom_lines, loc="upper right")
    
    ax.set_title("Rayong Coastal Analysis AOI Overview")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")

    plt.tight_layout()
    plt.savefig(out_png, dpi=300)
    print(f"Saved QA figure to {out_png}")

if __name__ == "__main__":
    main()
