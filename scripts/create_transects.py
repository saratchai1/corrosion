import geopandas as gpd
from shapely.geometry import LineString
import numpy as np

def create_transects(baseline, spacing=100, length=2000):
    transects = []
    distances = np.arange(0, baseline.length, spacing)
    for i, d in enumerate(distances):
        # Point on baseline
        pt = baseline.interpolate(d)
        
        # Get point a little bit ahead to calculate angle
        pt_ahead = baseline.interpolate(min(d + 1, baseline.length))
        if pt == pt_ahead:
            pt_ahead = baseline.interpolate(max(d - 1, 0))
            dx = pt.x - pt_ahead.x
            dy = pt.y - pt_ahead.y
        else:
            dx = pt_ahead.x - pt.x
            dy = pt_ahead.y - pt.y
            
        angle = np.arctan2(dy, dx)
        
        # Perpendicular angle
        perp_angle = angle + np.pi/2
        
        x1 = pt.x - (length/2) * np.cos(perp_angle)
        y1 = pt.y - (length/2) * np.sin(perp_angle)
        x2 = pt.x + (length/2) * np.cos(perp_angle)
        y2 = pt.y + (length/2) * np.sin(perp_angle)
        
        transects.append(LineString([(x1, y1), (x2, y2)]))
        
    return transects

def main():
    shoreline_gdf = gpd.read_file("data/analysis/rayong/shorelines/2025-02-09.geojson")
    shoreline_proj = shoreline_gdf.to_crs(epsg=32647)
    
    # Create a baseline by simplifying the shoreline
    # This is a basic approximation for prototype
    # Usually you manually draw a baseline or heavily smooth the shoreline
    geom = shoreline_proj.geometry.iloc[0]
    
    # We take the longest linestring in the multilinestring to act as main baseline
    if geom.geom_type == 'MultiLineString':
        lines = list(geom.geoms)
        lines.sort(key=lambda x: x.length, reverse=True)
        main_line = lines[0]
    else:
        main_line = geom
        
    # Simplify heavily (e.g. 500m tolerance) to get a smooth baseline
    baseline = main_line.simplify(500)
    
    lines = create_transects(baseline, spacing=100, length=2000)
    
    transect_gdf = gpd.GeoDataFrame(
        {"transect_id": [f"TR_{i:04d}" for i in range(len(lines))]},
        geometry=lines,
        crs="EPSG:32647"
    )
    
    out_path = "data/analysis/rayong/transects/rayong_transects.geojson"
    transect_gdf.to_crs(epsg=4326).to_file(out_path, driver="GeoJSON")
    print(f"Created {len(lines)} transects and saved to {out_path}")

if __name__ == "__main__":
    main()
