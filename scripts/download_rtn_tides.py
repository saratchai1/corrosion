#!/usr/bin/env python3
"""Download and parse Royal Thai Navy Hydrographic Department tide prediction PDFs.

Official source: https://hydro.navy.mi.th/waterlaveltable
Station codes used by RTN:
  PR = Pak Nam Rayong
  MT = Map Ta Phut
  LS = Laem Sing
"""
from __future__ import annotations
import csv, hashlib, json, re, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import requests
import pdfplumber

BKK = ZoneInfo("Asia/Bangkok")
UTC = timezone.utc

# RTN PDF URL pattern for the current waterlaveltable page (2026 / พ.ศ.2569)
# The article IDs are specific to each station/datum combination for 2026.
# For other years the IDs differ; we probe systematically.
STATIONS = {
    "pak_nam_rayong": {
        "code": "PR",
        "name": "Pak Nam Rayong",
        "lat": 12 + 39/60 + 26/3600,   # 12°39'26"N
        "lon": 101 + 16/60 + 34/3600,  # 101°16'34"E
    },
    "map_ta_phut": {
        "code": "MT",
        "name": "Map Ta Phut",
        "lat": 12 + 40/60 + 22/3600,   # 12°40'22"N
        "lon": 101 + 8/60 + 20/3600,   # 101°08'20"E
    },
    "laem_sing": {
        "code": "LS",
        "name": "Laem Sing",
        "lat": 12 + 28/60 + 31/3600,   # 12°28'31"N
        "lon": 102 + 3/60 + 31/3600,   # 102°03'31"E
    },
}

# Known 2026 article IDs from the waterlaveltable page
KNOWN_URLS_2026 = {
    "PR": {
        "llw": "https://hydro.navy.mi.th/storage/frontend/article/23000/file/th/PR2026.pdf",
        "msl": "https://hydro.navy.mi.th/storage/frontend/article/23001/file/th/PR2026msl.pdf",
    },
    "MT": {
        "llw": "https://hydro.navy.mi.th/storage/frontend/article/22998/file/th/MT2026.pdf",
        "msl": "https://hydro.navy.mi.th/storage/frontend/article/22999/file/th/MT2026msl.pdf",
    },
    "LS": {
        "llw": "https://hydro.navy.mi.th/storage/frontend/article/23002/file/th/LS2026.pdf",
        "msl": "https://hydro.navy.mi.th/storage/frontend/article/23003/file/th/LS2026msl.pdf",
    },
}

# For historical years, the RTN uses a different URL pattern on the older site
# We'll try the servicestide pattern: https://www.hydro.navy.mi.th/servicestide{YEAR}.html
# and also try direct PDF URLs with common patterns
def guess_historical_urls(code: str, year: int, datum: str = "msl") -> list[str]:
    """Generate candidate URLs for historical tide PDFs."""
    suffix = "msl" if datum == "msl" else ""
    fname = f"{code}{year}{suffix}.pdf" if suffix else f"{code}{year}.pdf"
    candidates = [
        f"https://hydro.navy.mi.th/storage/frontend/article/{aid}/file/th/{fname}"
        for aid in range(22980, 23050)  # scan a range of article IDs
    ]
    # Also try the old-format URL
    candidates.append(f"https://www.hydro.navy.mi.th/{fname}")
    candidates.append(f"https://hydro.navy.mi.th/{fname}")
    return candidates


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download_pdf(url: str, dest: Path, timeout: int = 30) -> bool:
    """Download a PDF. Returns True if successful."""
    try:
        resp = requests.get(url, timeout=timeout, allow_redirects=True)
        if resp.status_code == 200 and len(resp.content) > 1000:
            # Quick check it's actually a PDF
            if resp.content[:4] == b'%PDF':
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(resp.content)
                return True
        return False
    except Exception:
        return False


MONTH_NAMES = {
    "January": 1, "February": 2, "March": 3, "April": 4,
    "May": 5, "June": 6, "July": 7, "August": 8,
    "September": 9, "October": 10, "November": 11, "December": 12,
}


def parse_tide_pdf(pdf_path: Path, station_id: str, datum: str) -> list[dict]:
    """Parse an RTN tide PDF into hourly records.
    
    Returns list of dicts with keys:
      station_id, datetime_bangkok, datetime_utc, height_m, datum,
      prediction_type, source_pdf, qa_status
    """
    records = []
    pdf = pdfplumber.open(pdf_path)
    
    for page in pdf.pages:
        text = page.extract_text()
        if not text:
            continue
        
        # Find month/year header
        month_num = None
        year_num = None
        for mname, mnum in MONTH_NAMES.items():
            if mname in text:
                month_num = mnum
                # Find year (CE)
                year_match = re.search(rf'{mname}\s+(\d{{4}})', text)
                if year_match:
                    year_num = int(year_match.group(1))
                break
        
        if month_num is None or year_num is None:
            continue
        
        # Parse lines with tide data
        # Each data line starts with a day number (1-31) followed by 24 float values
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            # Match: starts with 1-2 digit number, then floats
            m = re.match(r'^(\d{1,2})\s+([-\d].*)', line)
            if not m:
                continue
            day = int(m.group(1))
            if day < 1 or day > 31:
                continue
            
            # Split the remaining values
            values_str = m.group(2)
            parts = values_str.split()
            
            # We expect 24 values for hours 0-23
            heights = []
            for p in parts:
                try:
                    heights.append(float(p))
                except ValueError:
                    break
            
            if len(heights) < 24:
                continue  # incomplete row, skip
            
            # Create records for each hour
            import calendar
            max_day = calendar.monthrange(year_num, month_num)[1]
            if day > max_day:
                continue
            
            for hour in range(24):
                dt_bkk = datetime(year_num, month_num, day, hour, 0, 0, tzinfo=BKK)
                dt_utc = dt_bkk.astimezone(UTC)
                records.append({
                    "station_id": station_id,
                    "datetime_bangkok": dt_bkk.strftime("%Y-%m-%dT%H:%M:%S+07:00"),
                    "datetime_utc": dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "height_m": heights[hour],
                    "datum": datum,
                    "prediction_type": "PREDICTED",
                    "source_pdf": str(pdf_path),
                    "qa_status": "parsed",
                })
    
    pdf.close()
    return records


def main():
    base_dir = Path("data/tide/rayong")
    raw_dir = base_dir / "raw"
    processed_dir = base_dir / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    
    manifest_path = base_dir / "tide_manifest.csv"
    manifest_rows = []
    
    # Download 2026 PDFs (MSL preferred)
    for station_id, info in STATIONS.items():
        code = info["code"]
        urls = KNOWN_URLS_2026.get(code, {})
        
        for datum, url in urls.items():
            dest = raw_dir / station_id / f"2026_{datum}.pdf"
            if dest.exists() and dest.stat().st_size > 1000:
                print(f"Already downloaded: {dest}")
                status = "downloaded"
            else:
                print(f"Downloading {url} -> {dest}")
                ok = download_pdf(url, dest)
                status = "downloaded" if ok else "failed"
                print(f"  Status: {status}")
            
            checksum = sha256_file(dest) if dest.exists() else ""
            
            # Parse if downloaded
            parser_status = "not_attempted"
            if status == "downloaded":
                try:
                    records = parse_tide_pdf(dest, station_id, datum.upper())
                    if records:
                        out_csv = processed_dir / f"{station_id}_2026_{datum}.csv"
                        with open(out_csv, "w", newline="") as f:
                            w = csv.DictWriter(f, fieldnames=list(records[0].keys()))
                            w.writeheader()
                            w.writerows(records)
                        print(f"  Parsed {len(records)} records -> {out_csv}")
                        parser_status = "parsed"
                    else:
                        parser_status = "no_records"
                except Exception as e:
                    parser_status = f"error: {e}"
                    print(f"  Parse error: {e}")
            
            manifest_rows.append({
                "station": station_id,
                "year": 2026,
                "datum": datum.upper(),
                "source_url": url,
                "download_status": status,
                "sha256": checksum,
                "parser_status": parser_status,
            })
    
    # Write manifest
    with open(manifest_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(manifest_rows[0].keys()))
        w.writeheader()
        w.writerows(manifest_rows)
    print(f"\nManifest written to {manifest_path}")


if __name__ == "__main__":
    main()
