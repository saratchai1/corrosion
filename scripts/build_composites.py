#!/usr/bin/env python3
"""Build same-grid median composites from AOI-clipped rasters.

Input files must already have matching CRS, bounds, resolution and band layout.
The script does not silently resample mixed Sentinel-2 10 m/20 m native bands.
"""
from pathlib import Path
import argparse, json, numpy as np, rasterio

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("inputs",nargs="+")
    ap.add_argument("--output",required=True)
    ap.add_argument("--nodata",type=float,default=None)
    a=ap.parse_args()
    srcs=[rasterio.open(p) for p in a.inputs]
    try:
        ref=srcs[0]
        sig=(ref.crs,ref.transform,ref.width,ref.height,ref.count)
        for s in srcs[1:]:
            if (s.crs,s.transform,s.width,s.height,s.count)!=sig:
                raise SystemExit(f"Grid mismatch: {s.name}; explicitly harmonize first")
        stack=[]
        for s in srcs:
            x=s.read(masked=True).astype("float32")
            stack.append(x.filled(np.nan))
        med=np.nanmedian(np.stack(stack),axis=0)
        profile=ref.profile.copy(); profile.update(driver="COG",dtype="float32",compress="DEFLATE",blocksize=512,nodata=a.nodata if a.nodata is not None else -9999.0)
        med=np.where(np.isnan(med),profile["nodata"],med).astype("float32")
        Path(a.output).parent.mkdir(parents=True,exist_ok=True)
        with rasterio.open(a.output,"w",**profile) as dst: dst.write(med)
        meta={"method":"median","inputs":[str(Path(p)) for p in a.inputs],"note":"Use dry/same-season inputs; tide matching must be evaluated from catalog metadata."}
        Path(a.output+".json").write_text(json.dumps(meta,indent=2))
    finally:
        for s in srcs: s.close()
if __name__=="__main__": main()
