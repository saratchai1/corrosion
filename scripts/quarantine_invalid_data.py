#!/usr/bin/env python3
import pandas as pd
import shutil
from pathlib import Path

def main():
    audit_df = pd.read_csv("data/analysis/rayong/satellite_footprint_audit.csv")
    
    quarantine_base = Path("data/quarantine/rayong_wrong_aoi")
    
    for _, row in audit_df.iterrows():
        if row["classification"] in ["SAMUT_SONGKHRAM", "OTHER", "AMBIGUOUS"]:
            src = Path(row["raster_path"])
            if not src.exists(): continue
            
            # Keep original structure in quarantine
            rel_path = src.relative_to("data/satellite")
            dst = quarantine_base / rel_path
            dst.parent.mkdir(parents=True, exist_ok=True)
            
            print(f"Moving {src} -> {dst}")
            shutil.move(src, dst)
            
            # Clean up empty parent directories
            try:
                src.parent.rmdir()
            except OSError:
                pass # not empty
                
    print("Quarantine complete.")

if __name__ == "__main__":
    main()
