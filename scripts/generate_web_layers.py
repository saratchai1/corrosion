#!/usr/bin/env python3
import rasterio
from rasterio.plot import reshape_as_image
from rasterio.warp import transform_bounds
import numpy as np
from PIL import Image
import json
import os
from pathlib import Path
import pandas as pd

def normalize(array):
    valid = array[np.isfinite(array)]
    if len(valid) == 0: return array
    p2, p98 = np.percentile(valid, (2, 98))
    return np.clip((array - p2) / max(p98 - p2, 0.001), 0, 1)

def calc_ndwi(green, nir):
    denom = (green + nir)
    denom[denom == 0] = 1e-6
    return (green - nir) / denom

def calc_mndwi(green, swir):
    denom = (green + swir)
    denom[denom == 0] = 1e-6
    return (green - swir) / denom

def map_index_to_rgba(idx_array, threshold=0):
    # blue for water (val > threshold), transparent otherwise
    rgba = np.zeros((*idx_array.shape, 4), dtype=np.uint8)
    water_mask = idx_array > threshold
    rgba[water_mask, 2] = 255 # blue
    rgba[water_mask, 3] = 150 # alpha
    return rgba

def generate_layers(scene_id, date_str):
    print(f"Generating web layers for {date_str} ({scene_id})...")
    # find scene dir
    scene_dir = None
    for y in ["2018", "2021", "2025"]:
        p = Path(f"data/satellite/sentinel2/{y}/{scene_id}")
        if p.exists():
            scene_dir = p
            break
            
    if not scene_dir:
        print(f"Scene dir not found for {scene_id}")
        return
        
    out_dir = Path("data/analysis/rayong/web/layers")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    with rasterio.open(scene_dir / "B4_10m.tif") as r, \
         rasterio.open(scene_dir / "B3_10m.tif") as g, \
         rasterio.open(scene_dir / "B2_10m.tif") as b, \
         rasterio.open(scene_dir / "B8_10m.tif") as nir:
         
        bounds = r.bounds
        crs = r.crs
        min_lon, min_lat, max_lon, max_lat = transform_bounds(crs, "EPSG:4326", *bounds)
        
        # Read and normalize
        r_arr = r.read(1).astype(float)
        g_arr = g.read(1).astype(float)
        b_arr = b.read(1).astype(float)
        nir_arr = nir.read(1).astype(float)
        
        # Resize B11 (20m) to 10m
        with rasterio.open(scene_dir / "B11_20m.tif") as swir1:
            swir_arr = swir1.read(1, out_shape=r_arr.shape).astype(float)
            
        rgb = np.dstack([normalize(r_arr), normalize(g_arr), normalize(b_arr)])
        fc = np.dstack([normalize(nir_arr), normalize(r_arr), normalize(g_arr)])
        
        ndwi = calc_ndwi(g_arr, nir_arr)
        mndwi = calc_mndwi(g_arr, swir_arr)
        
        # Convert to uint8
        rgb_u8 = (rgb * 255).astype(np.uint8)
        fc_u8 = (fc * 255).astype(np.uint8)
        
        ndwi_rgba = map_index_to_rgba(ndwi, 0)
        mndwi_rgba = map_index_to_rgba(mndwi, 0)
        
        # Save images
        Image.fromarray(rgb_u8).save(out_dir / f"{date_str}_rgb.png")
        Image.fromarray(fc_u8).save(out_dir / f"{date_str}_nir.png")
        Image.fromarray(ndwi_rgba).save(out_dir / f"{date_str}_ndwi.png")
        Image.fromarray(mndwi_rgba).save(out_dir / f"{date_str}_mndwi.png")
        
        return {
            "date": date_str,
            "scene_id": scene_id,
            "bounds": [[min_lat, min_lon], [max_lat, max_lon]], # Leaflet uses [ [lat, lon], [lat, lon] ]
            "rgb": f"layers/{date_str}_rgb.png",
            "nir": f"layers/{date_str}_nir.png",
            "ndwi": f"layers/{date_str}_ndwi.png",
            "mndwi": f"layers/{date_str}_mndwi.png",
            "water_edge": f"{date_str}_water_edge.geojson"
        }

def main():
    meta = []
    dates = [
        ("S2B_47PQQ_20180206_0_L2A", "2018-02-06"),
        ("S2B_47PQQ_20211227_0_L2A", "2021-12-27"),
        ("S2C_47PQQ_20251221_0_L2A", "2025-12-21")
    ]
    
    for s_id, d_str in dates:
        m = generate_layers(s_id, d_str)
        if m: meta.append(m)
        
    with open("data/analysis/rayong/web/screening_scenes.json", "w") as f:
        json.dump(meta, f, indent=2)

if __name__ == "__main__":
    main()
