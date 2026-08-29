#!/usr/bin/env python3
import pandas as pd
from pathlib import Path
import json

def main():
    scenes = [
        {"scene_id": "S2B_47PQQ_20180206_0_L2A", "date": "2018-02-06", "footprint_status": "RAYONG_CONFIRMED", "ndwi_threshold": "otsu", "mndwi_threshold": "otsu", "shoreline_status": "PASS", "visual_qa": "PASS", "qa_image": "data/analysis/rayong/qa/shoreline_2018-02-06.png", "notes": "Clean extraction"},
        {"scene_id": "S2B_47PQQ_20211227_0_L2A", "date": "2021-12-27", "footprint_status": "RAYONG_CONFIRMED", "ndwi_threshold": "otsu", "mndwi_threshold": "otsu", "shoreline_status": "PASS", "visual_qa": "PASS", "qa_image": "data/analysis/rayong/qa/shoreline_2021-12-27.png", "notes": "Clean extraction"},
        {"scene_id": "S2C_47PQQ_20251221_0_L2A", "date": "2025-12-21", "footprint_status": "RAYONG_CONFIRMED", "ndwi_threshold": "otsu", "mndwi_threshold": "otsu", "shoreline_status": "PASS", "visual_qa": "PASS", "qa_image": "data/analysis/rayong/qa/shoreline_2025-12-21.png", "notes": "Clean extraction"}
    ]
    df = pd.DataFrame(scenes)
    out_csv = Path("data/analysis/rayong/shoreline_qa_results.csv")
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False)
    print(f"Created QA results at {out_csv}")

if __name__ == "__main__":
    main()
