#!/usr/bin/env python3
"""Discover and optionally clip public satellite COGs to the Samut Songkhram AOI.

Default provider: Element 84 Earth Search STAC v1. No credentials are required for
catalog discovery. The script never downloads full scenes; rasterio windowed reads
are used against remote COG assets and outputs are written as compressed COGs.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

STAC = "https://earth-search.aws.element84.com/v1"
BKK = ZoneInfo("Asia/Bangkok")
FIELDS = ["dataset","scene_id","sensor","acquisition_datetime_utc","acquisition_datetime_bangkok","cloud_cover_scene","cloud_cover_aoi","tide_station","tide_level","tide_datum","tide_status","source_url","source_license","crs","resolution_m","bands","local_path","file_size_bytes","sha256","selection_reason","qa_status"]
COLLECTIONS = {
    "sentinel2": "sentinel-2-l2a",
    "landsat": "landsat-c2-l2",
    "sentinel1": "sentinel-1-grd",
}
LICENSES = {
    "sentinel2": "Copernicus Sentinel Data Legal Notice - free, full and open access",
    "sentinel1": "Copernicus Sentinel Data Legal Notice - free, full and open access",
    "landsat": "USGS Landsat - Public Domain / no restrictions on use",
}
BANDS = {
    "sentinel2": ["blue","green","red","nir","rededge1","rededge2","rededge3","nir08","swir16","swir22","scl"],
    "landsat": ["blue","green","red","nir08","swir16","swir22","qa_pixel"],
    "sentinel1": ["vv","vh"],
}

def load_geom(path: Path):
    obj=json.loads(path.read_text())
    return obj["features"][0]["geometry"]

def search(dataset, geom, start, end, limit=500):
    body={"collections":[COLLECTIONS[dataset]],"intersects":geom,"datetime":f"{start}/{end}","limit":limit}
    r=requests.post(f"{STAC}/search",json=body,timeout=120); r.raise_for_status()
    return r.json().get("features",[])

def dtpair(s):
    d=datetime.fromisoformat(s.replace("Z","+00:00")).astimezone(timezone.utc)
    return d.isoformat().replace("+00:00","Z"), d.astimezone(BKK).isoformat()

def sensor_name(dataset, props):
    if dataset=="sentinel2": return props.get("platform","Sentinel-2")
    if dataset=="sentinel1": return props.get("platform","Sentinel-1")
    return props.get("platform") or props.get("constellation") or "Landsat"

def cloud_scene(props):
    return props.get("eo:cloud_cover","")

def rank_items(dataset, items, per_year):
    # Candidate ranking only. AOI cloud fraction is calculated later from SCL/QA;
    # scene cloud is used merely as a first-pass ordering and is never represented
    # as AOI cloud cover.
    by={}
    for it in items:
        y=it["properties"]["datetime"][:4]; by.setdefault(y,[]).append(it)
    out=[]
    for y,arr in sorted(by.items()):
        arr.sort(key=lambda x:(x["properties"].get("eo:cloud_cover",1000),x["properties"]["datetime"]))
        out.extend(arr[:per_year])
    return out

def write_catalog(dataset, items, path):
    path.parent.mkdir(parents=True,exist_ok=True)
    rows=[]
    for it in items:
        p=it["properties"]; utc,bkk=dtpair(p["datetime"])
        rows.append({
            "dataset":dataset,"scene_id":it["id"],"sensor":sensor_name(dataset,p),
            "acquisition_datetime_utc":utc,"acquisition_datetime_bangkok":bkk,
            "cloud_cover_scene":cloud_scene(p),"cloud_cover_aoi":"",
            "tide_station":"","tide_level":"","tide_datum":"","tide_status":"unverified",
            "source_url":it.get("links",[{}])[0].get("href",STAC),"source_license":LICENSES[dataset],
            "crs":"EPSG:32647","resolution_m":"10/20" if dataset=="sentinel2" else ("30" if dataset=="landsat" else "native GRD; output grid defined by processing"),
            "bands":";".join(BANDS[dataset]),"local_path":"","file_size_bytes":"","sha256":"",
            "selection_reason":"candidate selected by AOI intersection and annual scene-cloud ranking; AOI cloud/tide still require verification",
            "qa_status":"candidate-unverified"})
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS); w.writeheader(); w.writerows(rows)

def sha256(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def clip_asset(href, geom4326, outpath, dst_crs="EPSG:32647"):
    # Import heavy geospatial stack only for download mode.
    import rasterio
    from rasterio.mask import mask
    from rasterio.vrt import WarpedVRT
    from rasterio.warp import transform_geom
    outpath.parent.mkdir(parents=True,exist_ok=True)
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.tiff,.jp2"):
        with rasterio.open(href) as src:
            g=transform_geom("EPSG:4326",src.crs,geom4326)
            data,tr=mask(src,[g],crop=True)
            prof=src.profile.copy(); prof.update(driver="GTiff",height=data.shape[1],width=data.shape[2],transform=tr,compress="DEFLATE",tiled=True,bigtiff="IF_SAFER")
            tmp=outpath.with_suffix(".tmp.tif")
            with rasterio.open(tmp,"w",**prof) as dst: dst.write(data)
        # Reproject while preserving source pixel size semantics; no 20 m Sentinel-2
        # band is claimed as genuine 10 m data.
        with rasterio.open(tmp) as src, WarpedVRT(src,crs=dst_crs) as vrt:
            profile=vrt.profile.copy(); profile.update(driver="COG",compress="DEFLATE",blocksize=512)
            with rasterio.open(outpath,"w",**profile) as dst:
                dst.write(vrt.read())
        tmp.unlink(missing_ok=True)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("dataset",choices=COLLECTIONS)
    ap.add_argument("--aoi",default="data/aoi/samut_songkhram_aoi.geojson")
    ap.add_argument("--start")
    ap.add_argument("--end",default=datetime.now(timezone.utc).date().isoformat())
    ap.add_argument("--per-year",type=int,default=4)
    ap.add_argument("--catalog")
    args=ap.parse_args()
    starts={"sentinel2":"2016-01-01","landsat":"1984-01-01","sentinel1":"2015-01-01"}
    geom=load_geom(Path(args.aoi)); start=args.start or starts[args.dataset]
    items=search(args.dataset,geom,start,args.end)
    chosen=rank_items(args.dataset,items,args.per_year)
    out=Path(args.catalog or f"data/catalog/{args.dataset}_scenes.csv")
    write_catalog(args.dataset,chosen,out)
    print(f"{args.dataset}: discovered={len(items)} selected_candidates={len(chosen)} catalog={out}")
    print("No raster was downloaded. Review AOI cloud/tide, then use clip_asset() or extend this script for approved assets.")

if __name__=="__main__": main()
