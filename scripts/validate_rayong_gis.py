import json
from pathlib import Path
import geopandas as gpd
from shapely.validation import explain_validity
from shapely.geometry import shape, GeometryCollection, Polygon, MultiPolygon
from shapely import make_valid
import pandas as pd
import numpy as np

def extract_polygons(geom):
    if geom.is_empty:
        return geom
    if geom.geom_type in ['Polygon', 'MultiPolygon']:
        return geom
    if geom.geom_type == 'GeometryCollection':
        polys = [g for g in geom.geoms if g.geom_type in ['Polygon', 'MultiPolygon']]
        if not polys:
            return Polygon()
        return MultiPolygon(polys) if len(polys) > 1 else polys[0]
    return Polygon()

def count_vertices(geom):
    if geom is None or geom.is_empty:
        return 0
    if geom.geom_type == 'Polygon':
        return len(geom.exterior.coords) + sum(len(i.coords) for i in geom.interiors)
    elif geom.geom_type == 'MultiPolygon':
        return sum(count_vertices(p) for p in geom.geoms)
    return 0

def get_polygon_count(geom):
    if geom is None or geom.is_empty:
        return 0
    if geom.geom_type == 'Polygon':
        return 1
    if geom.geom_type == 'MultiPolygon':
        return len(geom.geoms)
    return 0

def main():
    raw_path = "data/aoi/rayong_planting_plots_raw.geojson"
    val_path = "data/aoi/rayong_planting_plots_validated.geojson"
    out_csv = "data/analysis/rayong/gis_validation.csv"
    out_json = "data/analysis/rayong/gis_validation_summary.json"

    raw_gdf = gpd.read_file(raw_path)
    
    # Identify ID column
    cols = list(raw_gdf.columns)
    id_col = next((c for c in cols if 'id' in c.lower() or 'name' in c.lower() or 'plot' in c.lower()), cols[0])
    
    records = []
    validated_geoms = []
    
    # Project to EPSG:32647 for measurements
    raw_proj = raw_gdf.to_crs(epsg=32647)

    for i, row in raw_gdf.iterrows():
        orig_geom = row.geometry
        orig_geom_proj = raw_proj.geometry.iloc[i]
        
        plot_id = row[id_col]
        geom_type = orig_geom.geom_type
        is_valid = orig_geom.is_valid
        val_error = explain_validity(orig_geom) if not is_valid else "Valid Geometry"
        
        orig_area_rai = orig_geom_proj.area / 1600.0
        orig_vertices = count_vertices(orig_geom)
        orig_poly_count = get_polygon_count(orig_geom)
        
        repair_method = "None"
        rep_geom = orig_geom
        rep_geom_proj = orig_geom_proj
        
        if not is_valid:
            repair_method = "make_valid + extract_polygons"
            rep_geom = extract_polygons(make_valid(orig_geom))
            
            # If make_valid is completely broken, fallback to buffer(0)
            if not rep_geom.is_valid or rep_geom.is_empty:
                repair_method = "buffer(0)"
                rep_geom = orig_geom.buffer(0)

            # Need projected version for metrics
            # Easiest way is to put in a GeoSeries
            gs = gpd.GeoSeries([rep_geom], crs=raw_gdf.crs)
            rep_geom_proj = gs.to_crs(epsg=32647).iloc[0]

        validated_geoms.append(rep_geom)
        
        rep_area_rai = rep_geom_proj.area / 1600.0
        area_diff = abs(rep_area_rai - orig_area_rai)
        pct_diff = (area_diff / orig_area_rai * 100) if orig_area_rai > 0 else 0
        
        centroid_shift = orig_geom_proj.centroid.distance(rep_geom_proj.centroid)
        
        rep_vertices = count_vertices(rep_geom)
        rep_poly_count = get_polygon_count(rep_geom)
        
        flag_area = pct_diff > 0.5
        flag_shift = centroid_shift > 1.0
        flag_type = orig_geom.geom_type != rep_geom.geom_type
        flag_poly = orig_poly_count != rep_poly_count
        
        status = "PASS"
        if not is_valid:
            status = "REVIEW"
            if flag_area or flag_shift or flag_type or flag_poly:
                status = "FAIL"
                
        records.append({
            "plotId": plot_id,
            "geometry_type": geom_type,
            "original_validity": is_valid,
            "validation_error": val_error,
            "repair_method": repair_method,
            "original_area_rai": orig_area_rai,
            "repaired_area_rai": rep_area_rai,
            "absolute_area_difference": area_diff,
            "percentage_area_difference": pct_diff,
            "centroid_shift_m": centroid_shift,
            "original_vertex_count": orig_vertices,
            "repaired_vertex_count": rep_vertices,
            "original_polygon_count": orig_poly_count,
            "repaired_polygon_count": rep_poly_count,
            "status": status
        })

    df = pd.DataFrame(records)
    df.to_csv(out_csv, index=False)
    
    summary = {
        "raw_feature_count": len(raw_gdf),
        "validated_feature_count": len(validated_geoms),
        "invalid_feature_count": len(df[~df.original_validity]),
        "pass_count": len(df[df.status == 'PASS']),
        "review_count": len(df[df.status == 'REVIEW']),
        "fail_count": len(df[df.status == 'FAIL']),
        "max_area_change_pct": df.percentage_area_difference.max()
    }
    with open(out_json, "w") as f:
        json.dump(summary, f, indent=2)
        
    val_gdf = raw_gdf.copy()
    val_gdf.geometry = validated_geoms
    val_gdf.to_file(val_path, driver="GeoJSON")
    print(f"Validation complete. Saved to {out_csv} and {val_path}")

if __name__ == "__main__":
    main()
