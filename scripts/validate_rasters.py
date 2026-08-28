#!/usr/bin/env python3
"""Validate AOI-clipped rasters and emit QA JSON/checksums."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import rasterio
from rasterio.crs import CRS
from rasterio.warp import transform_bounds

def digest(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def validate(path):
    rec={"path":str(path),"sha256":digest(path),"size":path.stat().st_size,"errors":[],"warnings":[]}
    try:
        with rasterio.open(path) as s:
            rec.update(crs=str(s.crs),bounds=list(s.bounds),resolution=[abs(s.transform.a),abs(s.transform.e)],band_count=s.count,nodata=s.nodata,dtype=list(s.dtypes),driver=s.driver,tiled=bool(s.profile.get("tiled")))
            if not s.crs: rec["errors"].append("missing CRS")
            elif s.crs != CRS.from_epsg(32647): rec["warnings"].append("analysis raster is not EPSG:32647")
            if s.width==0 or s.height==0 or s.count==0: rec["errors"].append("empty raster dimensions")
            if s.crs:
                b=transform_bounds(s.crs,"EPSG:4326",*s.bounds,densify_pts=21)
                rec["bounds_epsg4326"]=list(b)
                # Broad sanity envelope around Samut Songkhram; catches gross geolocation errors only.
                if b[2]<99.85 or b[0]>100.15 or b[3]<13.20 or b[1]>13.55:
                    rec["errors"].append("raster does not intersect Samut Songkhram coastal sanity envelope")
            if s.nodata is None: rec["warnings"].append("nodata unset; verify mask/valid-data semantics")
            try:
                m=s.read_masks(1,out_shape=(1,min(512,s.height),min(512,s.width)))
                if not m.any(): rec["errors"].append("sample mask contains no valid pixels")
            except Exception as e: rec["warnings"].append(f"mask sample failed: {e}")
    except Exception as e: rec["errors"].append(str(e))
    rec["qa_status"]="fail" if rec["errors"] else ("review" if rec["warnings"] else "pass")
    return rec

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("paths",nargs="+"); ap.add_argument("--json",default="data/manifests/raster_validation.json"); ap.add_argument("--checksums",default="data/manifests/checksums.sha256"); a=ap.parse_args()
    rows=[validate(Path(x)) for x in a.paths]
    Path(a.json).parent.mkdir(parents=True,exist_ok=True); Path(a.json).write_text(json.dumps(rows,indent=2))
    Path(a.checksums).write_text("".join(f"{r['sha256']}  {r['path']}\n" for r in rows))
    for r in rows: print(r["qa_status"],r["path"],"; ".join(r["errors"]+r["warnings"]))
    raise SystemExit(1 if any(r["errors"] for r in rows) else 0)
if __name__=="__main__": main()
