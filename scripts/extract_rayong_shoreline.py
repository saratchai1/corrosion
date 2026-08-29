import rasterio
import rasterio.features
import numpy as np
import geopandas as gpd
from shapely.geometry import shape, MultiLineString
from pathlib import Path
import json

def calculate_ndwi(green_path, nir_path, scl_path):
    with rasterio.open(green_path) as src:
        green = src.read(1).astype(np.float32)
        transform = src.transform
        crs = src.crs
    with rasterio.open(nir_path) as src:
        nir = src.read(1).astype(np.float32)
    with rasterio.open(scl_path) as src:
        scl = src.read(1)
        
    # Mask no-data and clouds (SCL 3=cloud shadow, 8,9,10=clouds)
    valid_mask = (green > 0) & (nir > 0) & (~np.isin(scl, [3, 8, 9, 10, 0]))
    
    # Compute NDWI
    # handle division by zero
    np.seterr(divide='ignore', invalid='ignore')
    ndwi = (green - nir) / (green + nir)
    ndwi[~valid_mask] = np.nan
    return ndwi, transform, crs

def vectorize_shoreline(ndwi, transform, crs, threshold=0.0):
    water_mask = (ndwi > threshold).astype(np.uint8)
    # The water mask has 1 for water, 0 for land.
    # We want to extract the boundary.
    shapes = rasterio.features.shapes(water_mask, mask=np.isfinite(ndwi), transform=transform)
    
    lines = []
    for geom_dict, val in shapes:
        # We look at the exterior of the polygons
        # Actually rasterio shapes give polygons. The boundary is the linear ring.
        if val == 1: # Water polygons
            geom = shape(geom_dict)
            lines.append(geom.exterior)
            for interior in geom.interiors:
                lines.append(interior)
                
    if not lines:
        return gpd.GeoDataFrame(geometry=[], crs=crs)
        
    mline = MultiLineString(lines)
    gdf = gpd.GeoDataFrame(geometry=[mline], crs=crs)
    return gdf

def main():
    scene_dir = Path("data/satellite/sentinel2/2025/S2B_47PQQ_20250209_0_L2A")
    date_str = "2025-02-09"
    
    green_path = scene_dir / "B3_10m.tif"
    nir_path = scene_dir / "B8_10m.tif"
    scl_path = scene_dir / "SCL_20m.tif"
    
    # Since SCL is 20m, we need to upsample it to match 10m bands, or we just rely on rasterio 
    # to open it. Wait, if SCL is 20m, the array shape is different!
    # Let's resample SCL to 10m to match Green/NIR.
    
    with rasterio.open(green_path) as src:
        out_shape = (src.height, src.width)
        
    with rasterio.open(scl_path) as src:
        scl = src.read(1, out_shape=out_shape, resampling=rasterio.enums.Resampling.nearest)
        
    with rasterio.open(green_path) as src:
        green = src.read(1).astype(np.float32)
        transform = src.transform
        crs = src.crs
        
    with rasterio.open(nir_path) as src:
        nir = src.read(1).astype(np.float32)
        
    valid_mask = (green > 0) & (nir > 0) & (~np.isin(scl, [3, 8, 9, 10, 0]))
    np.seterr(divide='ignore', invalid='ignore')
    ndwi = (green - nir) / (green + nir)
    ndwi[~valid_mask] = np.nan
    
    threshold = 0.0
    gdf = vectorize_shoreline(ndwi, transform, crs, threshold=threshold)
    
    # Attach attributes
    gdf["scene_id"] = "S2B_47PQQ_20250209_0_L2A"
    gdf["date"] = date_str
    gdf["tide_level"] = "unverified"
    gdf["tide_station"] = "unverified"
    gdf["index_used"] = "NDWI"
    gdf["threshold"] = threshold
    gdf["source_sensor"] = "Sentinel-2"
    gdf["QA_flags"] = "initial_prototype"
    
    out_dir = Path("data/analysis/rayong/shorelines")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{date_str}.geojson"
    
    gdf.to_crs(epsg=4326).to_file(out_path, driver="GeoJSON")
    print(f"Shoreline extracted and saved to {out_path}")

if __name__ == "__main__":
    main()
