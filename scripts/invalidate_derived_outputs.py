#!/usr/bin/env python3
import pandas as pd
from pathlib import Path
import os
import shutil

def main():
    audit_df = pd.read_csv("data/analysis/rayong/satellite_footprint_audit.csv")
    valid_scenes = set(audit_df[audit_df["classification"] == "RAYONG_CONFIRMED"]["scene_id"])
    invalid_scenes = set(audit_df[audit_df["classification"].isin(["SAMUT_SONGKHRAM", "OTHER", "AMBIGUOUS"])]["scene_id"])
    
    # We will trace outputs by their date. 
    # Create mapping of date -> classification based on what scenes we have
    date_to_class = {}
    for _, row in audit_df.iterrows():
        # Sentinel-2 date extraction (e.g. S2B_47PQQ_20250209_0_L2A or S2B_MSIL2A_20200107T034129...)
        # We can extract the date from the output file names usually.
        pass

    results = []
    
    dirs_to_check = [
        Path("data/analysis/rayong/shorelines"),
        Path("data/analysis/rayong/qa"),
        Path("data/analysis/rayong/transects"),
        Path("data/analysis/rayong/change_metrics")
    ]
    
    for d in dirs_to_check:
        if not d.exists(): continue
        for f in d.iterdir():
            if f.is_file() and not f.name.startswith("."):
                # Extract date from filename, e.g. shoreline_2022-01-31.png or 2020-01-27_ndwi_otsu.geojson
                import re
                m = re.search(r'(\d{4}-\d{2}-\d{2})', f.name)
                if not m:
                    # check for YYYYMMDD without dashes
                    m2 = re.search(r'(\d{8})', f.name)
                    if m2:
                        date_str = f"{m2.group(1)[:4]}-{m2.group(1)[4:6]}-{m2.group(1)[6:8]}"
                    else:
                        date_str = None
                else:
                    date_str = m.group(1)
                    
                status = "UNKNOWN_SOURCE"
                reason = "Could not map to a scene"
                scene_class = "UNKNOWN"
                source_scene = "UNKNOWN"
                
                if date_str:
                    # Let's find if we have an audit row matching this date
                    date_compact = date_str.replace("-", "")
                    matching_rows = audit_df[audit_df["scene_id"].str.contains(date_compact)]
                    if len(matching_rows) > 0:
                        source_scene = matching_rows.iloc[0]["scene_id"]
                        scene_class = matching_rows.iloc[0]["classification"]
                        if scene_class == "RAYONG_CONFIRMED":
                            status = "VALID"
                            reason = "Matches confirmed Rayong footprint"
                        else:
                            status = "INVALID_WRONG_AOI"
                            reason = f"Derived from {scene_class} scene"
                    else:
                        status = "REGENERATE"
                        reason = "Source scene missing/deleted"
                
                results.append({
                    "output_path": str(f),
                    "source_scene": source_scene,
                    "source_scene_classification": scene_class,
                    "status": status,
                    "reason": reason
                })
                
                # If invalid, remove it
                if status in ["INVALID_WRONG_AOI", "REGENERATE", "UNKNOWN_SOURCE"]:
                    if status != "VALID":
                        f.unlink()
                        
    out_csv = Path("data/analysis/rayong/derived_output_audit.csv")
    pd.DataFrame(results).to_csv(out_csv, index=False)
    print(f"Invalidated and removed bad derived outputs. Logged to {out_csv}")

if __name__ == "__main__":
    main()
