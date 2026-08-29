import json
import geopandas as gpd

def main():
    plots_path = "data/aoi/rayong_planting_plots.geojson"
    aoi_path = "data/aoi/rayong_coastal_analysis_aoi.geojson"

    # Validate plots
    plots = gpd.read_file(plots_path)
    print("Rayong planting plots:")
    print(f"  Feature count: {len(plots)}")
    
    cols = list(plots.columns)
    id_col = next((c for c in cols if 'id' in c.lower() or 'name' in c.lower() or 'plot' in c.lower()), cols[0])
    print(f"  Plot IDs column used: {id_col}")
    print(f"  Plot IDs: {plots[id_col].tolist()}")
    
    print(f"  CRS: {plots.crs}")
    bounds = plots.total_bounds
    print(f"  bbox: {bounds}")
    
    # Approximate total area in hectares using local UTM (Rayong is in UTM 47N, EPSG:32647)
    plots_utm = plots.to_crs(epsg=32647)
    total_area_ha = plots_utm.geometry.area.sum() / 10000
    print(f"  Approximate total area (ha): {total_area_ha:.2f}")
    print(f"  Geometry validity: {plots.is_valid.all()}")
    if not plots.is_valid.all():
        print(f"  Invalid geometries found!")
        # Fix invalid geometries with buffer(0)
        plots['geometry'] = plots['geometry'].buffer(0)
        plots.to_file(plots_path, driver='GeoJSON')
        print("  Fixed invalid geometries using buffer(0) and saved back.")

    print("\nRayong analysis AOI:")
    aoi = gpd.read_file(aoi_path)
    print(f"  Feature count: {len(aoi)}")
    print(f"  CRS: {aoi.crs}")
    aoi_bounds = aoi.total_bounds
    print(f"  bbox: {aoi_bounds}")
    aoi_utm = aoi.to_crs(epsg=32647)
    aoi_area_ha = aoi_utm.geometry.area.sum() / 10000
    print(f"  Approximate area (ha): {aoi_area_ha:.2f}")
    
    print(f"  Geometry validity: {aoi.is_valid.all()}")
    if not aoi.is_valid.all():
        print("  Fixing invalid geometries in AOI...")
        aoi['geometry'] = aoi['geometry'].buffer(0)
        aoi.to_file(aoi_path, driver='GeoJSON')
        print("  Fixed invalid geometries and saved back.")

if __name__ == '__main__':
    main()
