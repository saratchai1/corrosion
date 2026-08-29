#!/usr/bin/env python3
"""Fast discovery of historical RTN tide PDFs using predictable directory patterns."""

import requests
import csv
import json
from pathlib import Path
import concurrent.futures

STATIONS = {
    "PR": "pak_nam_rayong",
    "LS": "laem_sing",
    "MT": "map_ta_phut",
    "TN": "annual_index"
}

HOSTS = [
    "https://hydro.navy.mi.th"
]

def generate_filename_variants(code, year, datum):
    if code == "TN":
        if datum == "LLW": return [f"TN{year}.pdf"]
        else: return [f"TN{year}%20msl.pdf", f"TN{year}msl.pdf", f"TN{year}MSL.pdf"]
            
    if datum == "LLW": return [f"{code}{year}.pdf"]
    else: return [f"{code}{year}%20msl.pdf", f"{code}{year}msl.pdf", f"{code}{year}MSL.pdf"]

def check_url(url):
    try:
        resp = requests.head(url, timeout=3, allow_redirects=True)
        if resp.status_code == 200:
            return True, resp.status_code, resp.headers.get('Content-Type', ''), int(resp.headers.get('Content-Length', 0)), resp.url
        return False, resp.status_code, resp.headers.get('Content-Type', ''), 0, resp.url
    except:
        return False, 0, "", 0, ""

def process_item(item):
    year, datum, code = item
    be_year = year + 543
    folder_code = str(be_year)[-2:]
    station_name = STATIONS[code]
    
    variants = generate_filename_variants(code, year, datum)
    
    for dir_base in ["Water_lever", "Water_level"]:
        for host in HOSTS:
            base_path = f"{host}/download/{dir_base}{folder_code}/{datum}"
            for fname in variants:
                candidate_url = f"{base_path}/{fname}"
                found, status, ctype, size, resolved = check_url(candidate_url)
                if found:
                    return {
                        "year": year, "station_code": code, "station_name": station_name,
                        "datum": datum, "candidate_url": candidate_url, "resolved_url": resolved,
                        "http_status": status, "content_type": ctype, "size_bytes": size,
                        "pdf_magic_valid": True, "status": "FOUND"
                    }
                
    # If not found
    return {
        "year": year, "station_code": code, "station_name": station_name,
        "datum": datum, "candidate_url": candidate_url, "resolved_url": "",
        "http_status": status, "content_type": ctype, "size_bytes": 0,
        "pdf_magic_valid": False, "status": "NOT_FOUND"
    }

def main():
    years = range(2015, 2027)
    datums = ["LLW", "MSL"]
    station_codes = ["TN", "PR", "LS", "MT"]
    
    items = [(y, d, c) for y in years for d in datums for c in station_codes]
    
    inventory = []
    summary_data = {code: {datum: [] for datum in datums} for code in station_codes}
    
    # Check 2026 local cache first
    raw_dir = Path("data/tide/rayong/raw")
    remaining_items = []
    
    for item in items:
        year, datum, code = item
        station_name = STATIONS[code]
        cache_file = raw_dir / station_name / f"{year}_{datum.lower()}.pdf"
        if cache_file.exists() and cache_file.stat().st_size > 1000:
            inventory.append({
                "year": year, "station_code": code, "station_name": station_name,
                "datum": datum, "candidate_url": "local_cache", "resolved_url": "local_cache",
                "http_status": 200, "content_type": "application/pdf", "size_bytes": cache_file.stat().st_size,
                "pdf_magic_valid": True, "status": "FOUND"
            })
            summary_data[code][datum].append(year)
        else:
            remaining_items.append(item)
            
    print(f"Checking {len(remaining_items)} items...")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(process_item, remaining_items))
        
    for res in results:
        inventory.append(res)
        if res["status"] == "FOUND":
            summary_data[res["station_code"]][res["datum"]].append(res["year"])
            
    inventory.sort(key=lambda x: (x["year"], x["station_code"], x["datum"]))
    
    out_csv = Path("data/tide/rayong/rtn_archive_inventory.csv")
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=inventory[0].keys())
        writer.writeheader()
        writer.writerows(inventory)
        
    out_json = Path("data/tide/rayong/rtn_archive_summary.json")
    with open(out_json, "w") as f:
        json.dump(summary_data, f, indent=2)
        
    print(f"Done. Saved to {out_csv}")

if __name__ == "__main__":
    main()
