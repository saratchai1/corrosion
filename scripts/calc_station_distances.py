#!/usr/bin/env python3
"""Calculate geodesic distances from tide stations to AOI and update stations.geojson."""
import json
import geopandas as gpd
from shapely.geometry import Point
from pyproj import Geod

STATIONS = {
    "pak_nam_rayong": {"name": "Pak Nam Rayong", "lat": 12 + 39/60 + 26/3600, "lon": 101 + 16/60 + 34/3600},
    "map_ta_phut": {"name": "Map Ta Phut", "lat": 12 + 40/60 + 22/3600, "lon": 101 + 8/60 + 20/3600},
    "laem_sing": {"name": "Laem Sing", "lat": 12 + 28/60 + 31/3600, "lon": 102 + 3/60 + 31/3600},
}

def main():
    aoi = gpd.read_file("data/aoi/rayong_coastal_analysis_aoi.geojson")
    aoi_geom = aoi.geometry.iloc[0]
    centroid = aoi_geom.centroid
    geod = Geod(ellps="WGS84")

    features = []
    for sid, info in STATIONS.items():
        pt = Point(info["lon"], info["lat"])
        
        # Distance to centroid
        _, _, dist_centroid = geod.inv(info["lon"], info["lat"], centroid.x, centroid.y)
        dist_centroid_km = dist_centroid / 1000
        
        # Distance to nearest AOI boundary point
        nearest_pt = aoi_geom.boundary.interpolate(aoi_geom.boundary.project(pt))
        _, _, dist_nearest = geod.inv(info["lon"], info["lat"], nearest_pt.x, nearest_pt.y)
        dist_nearest_km = dist_nearest / 1000
        
        # Assign role
        if sid == "pak_nam_rayong":
            role = "PRIMARY_WEST"
        elif sid == "laem_sing":
            role = "PRIMARY_EAST"
        else:
            role = "SECONDARY"
        
        print(f"{info['name']}: centroid={dist_centroid_km:.1f} km, nearest={dist_nearest_km:.1f} km, role={role}")
        
        features.append({
            "type": "Feature",
            "properties": {
                "station_id": sid,
                "station_name": info["name"],
                "latitude": round(info["lat"], 6),
                "longitude": round(info["lon"], 6),
                "source": "Hydrographic Department, Royal Thai Navy",
                "datum_options": "LLW, MSL",
                "distance_to_aoi_centroid_km": round(dist_centroid_km, 1),
                "distance_to_aoi_nearest_km": round(dist_nearest_km, 1),
                "role": role,
            },
            "geometry": {"type": "Point", "coordinates": [round(info["lon"], 6), round(info["lat"], 6)]},
        })

    geojson = {"type": "FeatureCollection", "features": features}
    out = "data/tide/rayong/stations.geojson"
    with open(out, "w") as f:
        json.dump(geojson, f, indent=2, ensure_ascii=False)
    print(f"\nSaved to {out}")

if __name__ == "__main__":
    main()
