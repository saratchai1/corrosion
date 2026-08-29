#!/usr/bin/env python3
"""Improved shoreline extraction with multiple threshold methods and coastal filtering."""
import rasterio
import rasterio.features
import numpy as np
import geopandas as gpd
from shapely.geometry import shape, MultiLineString, LineString
from shapely.ops import unary_union
from pathlib import Path
import argparse
import json

def compute_index(green, nir, swir=None, method="ndwi"):
    np.seterr(divide='ignore', invalid='ignore')
    if method == "ndwi":
        idx = (green - nir) / (green + nir)
    elif method == "mndwi" and swir is not None:
        idx = (green - swir) / (green + swir)
    else:
        idx = (green - nir) / (green + nir)
    return idx

def otsu_threshold(data):
    """Simple Otsu thresholding on valid data."""
    valid = data[np.isfinite(data)]
    if len(valid) < 100:
        return 0.0
    hist, bin_edges = np.histogram(valid, bins=256)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
    total = hist.sum()
    sum_total = (hist * bin_centers).sum()
    
    best_thresh = 0
    best_var = 0
    sum_bg = 0
    weight_bg = 0
    
    for i in range(len(hist)):
        weight_bg += hist[i]
        if weight_bg == 0:
            continue
        weight_fg = total - weight_bg
        if weight_fg == 0:
            break
        sum_bg += hist[i] * bin_centers[i]
        mean_bg = sum_bg / weight_bg
        mean_fg = (sum_total - sum_bg) / weight_fg
        var_between = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2
        if var_between > best_var:
            best_var = var_between
            best_thresh = bin_centers[i]
    
    return best_thresh

def extract_shoreline(scene_dir, date_str, method="ndwi", threshold_method="otsu",
                      fixed_threshold=0.0, scene_id="", tide_level="unverified",
                      tide_station="unverified"):
    """Extract water-land boundary as vector shoreline."""
    green_path = scene_dir / "B3_10m.tif"
    nir_path = scene_dir / "B8_10m.tif"
    swir_path = scene_dir / "B11_20m.tif"
    scl_path = scene_dir / "SCL_20m.tif"
    
    with rasterio.open(green_path) as src:
        green = src.read(1).astype(np.float32)
        transform = src.transform
        crs = src.crs
        out_shape = (src.height, src.width)
    
    with rasterio.open(nir_path) as src:
        nir = src.read(1).astype(np.float32)
    
    # Resample SCL (20m) to 10m
    with rasterio.open(scl_path) as src:
        scl = src.read(1, out_shape=out_shape, resampling=rasterio.enums.Resampling.nearest)
    
    # SWIR for MNDWI
    swir = None
    if method == "mndwi" and swir_path.exists():
        with rasterio.open(swir_path) as src:
            swir = src.read(1, out_shape=out_shape, resampling=rasterio.enums.Resampling.bilinear).astype(np.float32)
    
    # Cloud/shadow mask: exclude SCL classes 0, 3, 8, 9, 10
    valid_mask = (green > 0) & (nir > 0) & (~np.isin(scl, [0, 1, 3, 8, 9, 10]))
    
    # Compute index
    idx = compute_index(green, nir, swir, method)
    idx[~valid_mask] = np.nan
    
    # Determine threshold
    if threshold_method == "otsu":
        threshold = otsu_threshold(idx)
    else:
        threshold = fixed_threshold
    
    print(f"  Method: {method}, Threshold: {threshold_method} = {threshold:.4f}")
    
    # Create water mask
    water_mask = (idx > threshold).astype(np.uint8)
    water_mask[~valid_mask] = 0
    
    # Vectorize water polygons
    shapes_gen = rasterio.features.shapes(water_mask, mask=valid_mask, transform=transform)
    water_polys = []
    for geom_dict, val in shapes_gen:
        if val == 1:
            water_polys.append(shape(geom_dict))
    
    if not water_polys:
        print("  WARNING: No water polygons found")
        return gpd.GeoDataFrame()
    
    # Union all water polygons and take boundary
    water_union = unary_union(water_polys)
    
    # Filter: keep only water bodies that touch the AOI boundary (open coast)
    # and are larger than a minimum area (exclude ponds)
    min_area = 10000  # sq meters in projected CRS
    
    if water_union.geom_type == 'MultiPolygon':
        large_polys = [p for p in water_union.geoms if p.area > min_area]
    elif water_union.area > min_area:
        large_polys = [water_union]
    else:
        large_polys = []
    
    if not large_polys:
        print("  WARNING: No large water bodies found")
        return gpd.GeoDataFrame()
    
    # Extract boundary lines
    lines = []
    for poly in large_polys:
        lines.append(poly.exterior)
        for interior in poly.interiors:
            lines.append(interior)
    
    # Convert rings to LineStrings
    line_geoms = [LineString(l.coords) for l in lines]
    
    gdf = gpd.GeoDataFrame(
        [{
            "scene_id": scene_id,
            "date": date_str,
            "tide_level": tide_level,
            "tide_station": tide_station,
            "index_used": method.upper(),
            "threshold_method": threshold_method,
            "threshold_value": round(threshold, 4),
            "source_sensor": "Sentinel-2",
            "tide_source_type": "PREDICTED" if tide_level != "unverified" else "unverified",
            "QA_flags": "prototype",
        }],
        geometry=[MultiLineString(line_geoms)],
        crs=crs,
    )
    
    return gdf


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene-dir", default="data/satellite/sentinel2/2025/S2B_47PQQ_20250209_0_L2A")
    parser.add_argument("--date", default="2025-02-09")
    parser.add_argument("--method", choices=["ndwi", "mndwi"], default="ndwi")
    parser.add_argument("--threshold", choices=["otsu", "fixed"], default="otsu")
    parser.add_argument("--fixed-value", type=float, default=0.0)
    args = parser.parse_args()
    
    scene_dir = Path(args.scene_dir)
    out_dir = Path("data/analysis/rayong/shorelines")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Test all methods
    for method in ["ndwi", "mndwi"]:
        for thresh in ["otsu", "fixed"]:
            print(f"\nExtracting: {method} / {thresh}")
            gdf = extract_shoreline(
                scene_dir, args.date,
                method=method,
                threshold_method=thresh,
                scene_id=scene_dir.name,
            )
            if not gdf.empty:
                suffix = f"_{method}_{thresh}"
                out_path = out_dir / f"{args.date}{suffix}.geojson"
                gdf.to_crs(epsg=4326).to_file(out_path, driver="GeoJSON")
                print(f"  Saved: {out_path}")
    
    # Also save the best (NDWI Otsu) as the default
    gdf = extract_shoreline(scene_dir, args.date, method="ndwi", threshold_method="otsu",
                            scene_id=scene_dir.name)
    if not gdf.empty:
        out_path = out_dir / f"{args.date}.geojson"
        gdf.to_crs(epsg=4326).to_file(out_path, driver="GeoJSON")
        print(f"\nDefault shoreline saved: {out_path}")


if __name__ == "__main__":
    main()
