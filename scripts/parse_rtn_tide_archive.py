#!/usr/bin/env python3
"""Parse all raw RTN tide PDFs found in the data/tide/rayong/raw directory."""

import csv
import json
from pathlib import Path
import pdfplumber
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import calendar

BKK = ZoneInfo("Asia/Bangkok")
UTC = timezone.utc

MONTH_NAMES = {
    "January": 1, "February": 2, "March": 3, "April": 4,
    "May": 5, "June": 6, "July": 7, "August": 8,
    "September": 9, "October": 10, "November": 11, "December": 12,
}

# RTN files often have Thai month names as well, but usually include English month names 
# Let's add Thai month names just in case older years don't have English
THAI_MONTHS = {
    "มกราคม": 1, "กุมภาพันธ์": 2, "มีนาคม": 3, "เมษายน": 4,
    "พฤษภาคม": 5, "มิถุนายน": 6, "กรกฎาคม": 7, "สิงหาคม": 8,
    "กันยายน": 9, "ตุลาคม": 10, "พฤศจิกายน": 11, "ธันวาคม": 12
}

MONTH_NAMES.update(THAI_MONTHS)

def parse_tide_pdf(pdf_path: Path, station_id: str, datum: str, expected_year: int) -> list[dict]:
    records = []
    
    try:
        pdf = pdfplumber.open(pdf_path)
    except Exception as e:
        print(f"Error opening {pdf_path}: {e}")
        return records
        
    for page in pdf.pages:
        text = page.extract_text()
        if not text:
            continue
            
        month_num = None
        
        # Check for month
        for mname, mnum in MONTH_NAMES.items():
            if mname in text:
                month_num = mnum
                break
                
        if month_num is None:
            continue
            
        # Lines with tide data usually start with day 1-31
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            # Match 1-31 followed by a bunch of floats (possibly negative)
            m = re.match(r'^(\d{1,2})\s+([-\d].*)', line)
            if not m:
                continue
                
            day = int(m.group(1))
            if day < 1 or day > 31:
                continue
                
            # Split remaining string into values
            parts = m.group(2).split()
            heights = []
            for p in parts:
                try:
                    heights.append(float(p))
                except ValueError:
                    break
                    
            # Need 24 hourly values
            if len(heights) < 24:
                continue
                
            try:
                max_day = calendar.monthrange(expected_year, month_num)[1]
            except ValueError:
                continue # Bad year/month combination
                
            if day > max_day:
                continue
                
            for hour in range(24):
                dt_bkk = datetime(expected_year, month_num, day, hour, 0, 0, tzinfo=BKK)
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
    
    # Sort and check for missing hours/duplicates
    if not records:
        return records
        
    records.sort(key=lambda x: x["datetime_utc"])
    
    # Simple QA
    is_leap = calendar.isleap(expected_year)
    expected_hours = 8784 if is_leap else 8760
    
    unique_times = set(r["datetime_utc"] for r in records)
    
    if len(records) != expected_hours:
        print(f"  WARNING: Expected {expected_hours} hours, parsed {len(records)} hours.")
    if len(unique_times) != len(records):
        print(f"  WARNING: Found {len(records) - len(unique_times)} duplicate timestamps.")
        
    return records

def main():
    raw_dir = Path("data/tide/rayong/raw")
    processed_dir = Path("data/tide/rayong/processed")
    processed_dir.mkdir(parents=True, exist_ok=True)
    
    if not raw_dir.exists():
        print("No raw directory found.")
        return
        
    for station_dir in raw_dir.iterdir():
        if not station_dir.is_dir():
            continue
            
        station_id = station_dir.name
        if station_id == "annual_index":
            continue
            
        for pdf_file in station_dir.glob("*.pdf"):
            # Expected format: 2025_msl.pdf
            m = re.match(r'^(\d{4})_(llw|msl)\.pdf$', pdf_file.name)
            if not m:
                continue
                
            year = int(m.group(1))
            datum = m.group(2).upper()
            
            out_csv = processed_dir / f"{station_id}_{year}_{datum.lower()}.csv"
            if out_csv.exists():
                # print(f"Already processed: {out_csv.name}")
                continue
                
            print(f"Parsing {pdf_file.name} for {station_id}...")
            records = parse_tide_pdf(pdf_file, station_id, datum, year)
            
            if records:
                with open(out_csv, "w", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=list(records[0].keys()))
                    writer.writeheader()
                    writer.writerows(records)
                print(f"  -> Saved {len(records)} records to {out_csv.name}")
            else:
                print(f"  -> FAILED to parse any records.")

if __name__ == "__main__":
    main()
