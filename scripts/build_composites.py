#!/usr/bin/env python3
"""Build a same-grid median composite for one band from AOI COGs.

Input files must already have matching CRS, bounds, resolution and band layout.
The script does not silently resample mixed Sentinel-2 10 m/20 m native bands.
"""
from pathlib import Path
import argparse
import json
import warnings

import numpy as np
import rasterio

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
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            med=np.nanmedian(np.stack(stack),axis=0)
        profile=ref.profile.copy()
        profile.update(
            driver="COG",
            dtype="float32",
            compress="DEFLATE",
            blocksize=512,
            nodata=a.nodata if a.nodata is not None else -9999.0,
        )
        med=np.where(np.isnan(med),profile["nodata"],med).astype("float32")
        Path(a.output).parent.mkdir(parents=True,exist_ok=True)
        with rasterio.open(a.output,"w",**profile) as dst:
            dst.write(med)
            dst.update_tags(
                composite_method="median",
                input_count=str(len(a.inputs)),
                source_inputs=";".join(str(Path(p)) for p in a.inputs),
            )
        meta={
            "method":"median",
            "inputs":[str(Path(p)) for p in a.inputs],
            "note":"Use dry/same-season inputs; tide matching must be evaluated from catalog metadata.",
        }
        Path(a.output+".json").write_text(json.dumps(meta,indent=2))
        from download_satellite_data import update_manifests

        update_manifests()
    finally:
        for s in srcs: s.close()
if __name__=="__main__": main()
